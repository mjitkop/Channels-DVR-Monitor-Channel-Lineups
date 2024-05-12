"""
Author: Gildas Lefur (a.k.a. "mjitkop" in the Channels DVR forums)

Description: This script monitors the channel lineups on a Channels DVR server.
             If changes are detected, it may send an email and/or text message
             as specified in the input arguments.

Disclaimer: this is an unofficial script that is NOT supported by the developers
            of Channels DVR.

For bug reports and support, go to: 
https://community.getchannels.com/t/python-script-to-be-notified-of-channel-changes/36464?u=mjitkop

Version History:
- 2023.06.01.2301: Initial public release.
- 2023.06.04.2229: Improved: don't use MIME to format messages (nicer SMS)
- 2023.06.08.1150: Improved: use MIME to convert to UTF-8 for emails only

- 2.0.0 : [IMPROVED] Save channel lineups to files
          [IMPROVED] Add error handling for situations where the DVR isn't found
          [FIXED] Need to handle the case when a source is added while the script is NOT running
          [FIXED] Don't ignore duplicate channels
          [NEW] Option '-l', '--log': Log channel changes to a file
- 2.1.0 : [CHANGED] Show lineup changes in order of channel numbers.
          [CHANGED] Show channel changes in order of channel names.
- 2.2.0 : [IMPROVED] Added "Channels DVR lineup changes:" as first line in SMS message
          [NEW] Show duplicated channels in each modified source
- 3.0.0 : [IMPROVED] Save reference files and the log file into a subdirectory that is
                     named using the IP address and the port number of the server
                     (better support for multiple servers)
          [IMPROVED] When displaying duplicated channels, show the channel numbers
                     without square brackets and without quotes (just the numbers)
          [IMPROVED] Some cosmetic changes to increase readability in the
                     detailed message
          [NEW] Added the server URL as the first line of the detailed message
                (useful information when monitoring multiple servers)
          [NEW] Added the source URL (used in the source settings) below the source 
                name in the detailed message
          [NEW] Added the starting channel number of the modified source when
                displaying the "Lineup changes" header
          [NEW] Added the DVR URL on the second line of the SMS message (useful
                information when monitoring multiple servers)
- 3.1.0 : [IMPROVED] Typo in the name of the data sub-directory
          [CHANGED] Logging the lineup changes is a standard feature now
          [CHANGED] The log file will contain the lineup changes of the current year.
                    A new file is created every year with the year number in the name.
          [NEW] File "last_activity.log" to log the result of the last check only
- 3.2.0 : [IMPROVED] Ignore sources that have the "Lineup" field empty
          [FIXED] Crash when a new source with zero channels is detected
          [NEW] Detect, report, and back up removed sources (in "Deleted_Sources" subdirectory)
"""

################################################################################
#                                                                              #
#                                   IMPORTS                                    #
#                                                                              #
################################################################################

import argparse, glob, os, requests, smtplib, sys, time

from datetime import datetime, timedelta
from email.mime.text import MIMEText

################################################################################
#                                                                              #
#                                  CONSTANTS                                   #
#                                                                              #
################################################################################

DEFAULT_PORT_NUMBER  = '8089'
DELETED_SOURCES_DIR  = 'Deleted_Sources'
EMAIL_SUBJECT        = 'Channels DVR: changes in channel lineups'
LOG_FILE_CHANGES     = 'channel_lineup_changes.log'
LOG_FILE_ACTIVITY    = 'last_activity.log'
LOOPBACK_ADDRESS     = '127.0.0.1'
SEPARATOR_CHARACTER  = '='
SMTP_PORT            = 587
SMTP_SERVER_ADDRESS  = {
                        'gmail'  : 'smtp.gmail.com', 
                        'outlook': 'smtp-mail.outlook.com', 
                        'yahoo'  : 'smtp.mail.yahoo.com'
                       }
VERSION              = '3.2.0'

################################################################################
#                                                                              #
#                               GLOBAL VARIABLES                               #
#                                                                              #
################################################################################
Data_Subdirectory_Path = None

################################################################################
#                                                                              #
#                                   CLASSES                                    #
#                                                                              #
################################################################################

class ChannelInfo:
    '''Attributes and methods to handle one channel.'''
    def __init__(self, channel_json) -> None:
        '''Initialize the attributes of this channel.'''
        self.id     = channel_json.get('ID', None)
        self.number = channel_json['GuideNumber']
        self.name   = channel_json['GuideName']
        self.hd     = channel_json.get('HD', None)

    def is_hd(self) -> bool:
        '''Return True if this is an HD channel.'''
        return self.hd == 1

class ChannelsDVRSource:
    '''Attributes and methods to handle one channel source.'''
    def __init__(self, source_json):
        '''Initialize the attributes of this source.'''
        self.source = source_json
        self.current_lineup  = None
        self.name = self.source['FriendlyName']
        self.previous_lineup = None
        self.url = None

    def delete_lineup_file(self):
        '''
        Delete the text file that contains the channel lineup of this source.
        '''
        if not self.is_new():
            file_name = create_local_file_name(self.name)
            if os.path.exists(file_name):
                os.remove(file_name)

    def get_added_channel_numbers(self):
        '''
        Compare the previous and current channel lineups and return the 
        new channel numbers that only appear in the current lineup.
        '''
        added_channels = {}

        previous_set = set(self.previous_lineup)
        current_set  = set(self.current_lineup)
        new_channel_numbers = list(current_set.difference(previous_set))
        
        for number in new_channel_numbers:
            added_channels[number] = self.current_lineup[number]

        return added_channels
    
    def get_channel_count_difference(self):
        '''
        Calculate the channel count difference between the current and previous lineups.
        Return a string that represents a signed version of the channel count ("-3", "+2"), or "=" if same numbers.
        '''
        channel_count_diff = len(self.current_lineup) - len(self.previous_lineup)
        
        if channel_count_diff != 0:
            channel_count_diff = "{:+}".format(channel_count_diff)
        else:
            channel_count_diff = "="

        return channel_count_diff

    def get_current_lineup_from_server(self):
        '''
        Extract the channel lineup from the provided source.
        Return a dictionary: {<channel number>:<class ChannelInfo instance>, ..., <channel number>:<class ChannelInfo instance>}
        '''
        current_channels = {}

        for channel_json in self.source['Channels']:
            channel_info = ChannelInfo(channel_json)
            current_channels[channel_info.number] = channel_info
        
        return current_channels
        
    def get_current_lineup_indexed_by_channel_names(self):
        '''
        Parse the current lineup that is indexed by channel numbers and create a new
        dictionary that is indexed by the channel names.
        '''
        lineup_by_channel_names = {}

        for _, channel_info in self.current_lineup.items():
            name = channel_info.name
            existing_list = lineup_by_channel_names.get(name, [])
            existing_list.append(channel_info)
            lineup_by_channel_names[name] = existing_list

        return lineup_by_channel_names

    def get_deleted_channel_numbers(self):
        '''
        Compare the previous and current channel lineups and return the 
        channels whose numbers only appear in the previous lineup.
        '''
        deleted_channels = {}
        
        previous_set = set(self.previous_lineup)
        current_set  = set(self.current_lineup)
        removed_channel_numbers = list(previous_set.difference(current_set))
        
        for number in removed_channel_numbers:
            deleted_channels[number] = self.previous_lineup[number]

        return deleted_channels
    
    def get_duplicate_channels(self):
        '''
        Return a list of channels whose names appear on more than one channel number.
        '''
        duplicate_channels = {}

        for name, channel_info_list in self.get_current_lineup_indexed_by_channel_names().items():
            if len(channel_info_list) > 1:
                duplicate_channels[name] = channel_info_list

        return duplicate_channels 

    def get_modified_channels(self):
        '''
        Compare the channel names at the same channel numbers between the current channel lineup and the previous one.
        Return the list of modified channels (different channel names at the same numbers).
        '''
        modified_channels = {}

        for number, previous_channel_info in self.previous_lineup.items():
            current_channel_info = self.current_lineup.get(number, None)

            if current_channel_info:
                if current_channel_info.name != previous_channel_info.name:
                    modified_channels[number] = (previous_channel_info, current_channel_info)

        return modified_channels

    def get_new_channel_names(self):
        '''
        Return the new channel names that were not present in the previous channel lineup.
        '''
        new_channels = {}

        previous_set = set(get_sorted_unique_channel_names_from_lineup(self.previous_lineup))
        current_set  = set(get_sorted_unique_channel_names_from_lineup(self.current_lineup))
        new_channel_names = list(current_set.difference(previous_set))
        
        for name in new_channel_names:
            for _, new_channel_info in self.current_lineup.items():
                if name == new_channel_info.name:
                    break
            new_channels[name] = new_channel_info

        return new_channels

    def get_previous_lineup_from_file(self):
        '''
        Read the saved lineup from the file whose title matches the name of this source.
        If a file for this source doesn't exist (i.e. the source is new), return an empty dictionary.
        '''
        reference_lineup = {}
        file_name = create_local_file_name(self.name)

        if os.path.exists(file_name):
            with open(file_name) as txt_file:
                lines = txt_file.read().splitlines()

            for line in lines:
                channel_json = {}

                channel_number = line.split(SEPARATOR_CHARACTER)[0]
                channel_name   = line.split(SEPARATOR_CHARACTER)[1]

                channel_json['GuideNumber'] = channel_number
                channel_json['GuideName']   = channel_name

                reference_lineup[channel_number] = ChannelInfo(channel_json)

        return reference_lineup

    def get_removed_channel_names(self):
        '''
        Compare the previous and current channel lineups and return the 
        channels whose names only appear in the previous lineup.
        '''
        removed_channels = {}
        
        previous_set = set(get_sorted_unique_channel_names_from_lineup(self.previous_lineup))
        current_set  = set(get_sorted_unique_channel_names_from_lineup(self.current_lineup))
        removed_channel_names = list(previous_set.difference(current_set))
        
        for name in removed_channel_names:
            for _, old_channel_info in self.previous_lineup.items():
                if name == old_channel_info.name:
                    break
            removed_channels[name] = old_channel_info

        return removed_channels

    def has_lineup_changes(self):
        '''
        Return a boolean: True if anything is different between the current and previous channel lineups.
        '''
        deleted  = self.get_deleted_channel_numbers()
        added    = self.get_added_channel_numbers()
        modified = self.get_modified_channels()
        removed  = self.get_removed_channel_names()
        new      = self.get_new_channel_names()

        is_lineup_different = any([tmp != {} for tmp in [deleted, added, modified, removed, new]])

        return is_lineup_different

    def is_empty(self):
        '''Return True if this source has zero channels.'''
        return len(self.current_lineup) == 0

    def is_new(self):
        '''
        Return a boolean: True when there is no existing channel lineup text file for this source.
        '''
        full_path = create_local_file_name(self.name)
        is_source_new = not os.path.exists(full_path)

        return is_source_new

    def save_channel_lineup_to_file(self):
        '''
        Replace the content of the text file that contains the channel lineup of this source
        with the current channel lineup.
        '''
        self.delete_lineup_file()

        if self.is_empty():
            # Create an empty file
            with open(create_local_file_name(self.name), 'w') as txt_file:
                pass 
        else:
            with open(create_local_file_name(self.name), 'a') as txt_file:
                sorted_channel_numbers = sort_dictionary_keys(self.current_lineup)

                for channel_number in sorted_channel_numbers:
                    channel_info = self.current_lineup[channel_number]
                    channel_name = channel_info.name
                    line_to_write = f'{channel_number}{SEPARATOR_CHARACTER}{channel_name}\n'
                    txt_file.write(line_to_write)

class LogFile:
    '''Attributes and methods to manage the log file'''
    def __init__(self) -> None:
        self.name = self._create_new_file_name()

    def _create_new_file_name(self):
        '''Create a new proper name for the log file.'''
        this_year = datetime.now().strftime('%Y')

        return create_local_file_name(this_year + '_' + LOG_FILE_CHANGES)
    
    def _is_new_file(self):
        '''Return True if the file doesn't exist on the disk.'''
        return not os.path.exists(self.name)

    def write(self, message):
        '''Write the given message to the log file'''
        self.name = self._create_new_file_name()

        if self._is_new_file():
            print(f'Channel lineup changes will be written to:\n{self.name}\n\n')

        string_to_write = datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '\n\n'
        string_to_write += message
        string_to_write += '\n****************************************************\n\n'

        with open(self.name, 'a') as log_file:
            log_file.write(string_to_write)

################################################################################
#                                                                              #
#                                  FUNCTIONS                                   #
#                                                                              #
################################################################################

def create_data_subdirectory(ip_address, port_number):
    '''
    Create a directory with the path as:
    current directory + "_<ip_address>-<port_number>_data" at the end
    '''
    global Data_Subdirectory_Path

    end_of_path = f'{ip_address}-{port_number}_data'
    data_subdirectory_path = os.path.join(os.getcwd(), end_of_path)

    if not os.path.exists(data_subdirectory_path):
        os.mkdir(data_subdirectory_path)
        
    Data_Subdirectory_Path = data_subdirectory_path

def create_detailed_message(dvr_url, server_version, sources):
    '''
    Generate a string that is easy to read in an email.
    It will start with the version of the Channels DVR server.
    Then it will list the removed channels, added channels, and modified
    channels for each source in order of the channel numbers as follows:
    
        Source name:
        - channel number 1 : name of removed channel 1
        ! channel number 2 : new channel name (was old channel name)
        - channel number 3 : name of removed channel 3
          ...
        + channel number 4 : name of added channel 4
        + channel number 5 : name of added channel 5
        ! channel number 6 : new channel name (was old channel name)
        + ...
        + channel number N : name of added channel N
        
    Bonus: when pasting this message as is in the Channels DVR forum and choosing
    the formatted text option, the removed channels are automatically highlighted 
    in red, and the added channels in green.
    
    For each source that was modified, the new channel count will also be shown
    with the channel count difference in parenthesis compared to the last count.
    Example:
        "Pluto TV channel count: 358 (-2)"    
    '''
    message = f'Channels DVR server URL: {dvr_url}\n'
    message += f'Channels DVR version: {server_version}\n'

    deleted_sources = get_deleted_sources(sources)
    if deleted_sources:
        message += '\n------------------------------\n\n'

        for source_name in deleted_sources:
            message += f'Deleted source: "{source_name}"\n'
    
    for source in sources:
        if source.is_new():
            message += '\n------------------------------\n\n'

            number_of_channels = len(source.current_lineup)
            message += f'New source with {number_of_channels} channels: "{source.name}"\n'
            file_name = create_local_file_name(source.name)
            if not source.is_empty():
                message += f'See file {file_name} for the full lineup.\n'
        else:
            if source.has_lineup_changes():
                deleted_channels    = source.get_deleted_channel_numbers()
                added_channels      = source.get_added_channel_numbers()
                modified_channels   = source.get_modified_channels()
                removed_channels    = source.get_removed_channel_names()
                new_channels        = source.get_new_channel_names()
                duplicated_channels = source.get_duplicate_channels()

                sorted_names   = get_sorted_channel_names_from_channel_changes(removed_channels, new_channels)
                sorted_numbers = get_sorted_channel_numbers_from_lineup_changes(deleted_channels, added_channels, modified_channels)

                message += '\n------------------------------\n\n'

                channel_count_diff = source.get_channel_count_difference()
                message += f'{source.name}: {len(source.current_lineup)} channels ({channel_count_diff})\n'

                source_url = get_source_url(dvr_url, source.name)
                if source_url:
                    message += f'({source_url})\n'

                if removed_channels or new_channels or duplicated_channels:
                    if not source.is_empty():
                        starting_channel_number = sorted(list(source.current_lineup.keys()))[0]
                        message += f'\n<--- Lineup changes (starting at {starting_channel_number}) --->\n'

                for number in sorted_numbers:
                    if number in list(deleted_channels.keys()):
                        channel_info = deleted_channels[number]
                        message += f'- {number} : {channel_info.name}\n'
                    if number in list(added_channels.keys()):    
                        channel_info = added_channels[number]
                        message += f'+ {number} : {channel_info.name}\n'
                    if number in list(modified_channels.keys()):
                        old_channel_info = modified_channels[number][0]
                        new_channel_info = modified_channels[number][1]
                        message += f'! {number} : {new_channel_info.name} (was {old_channel_info.name})\n'
                    
                if removed_channels or new_channels:
                    message += '\n<--- Channel changes --->\n'
                
                for name in sorted_names:
                    if name in list(removed_channels.keys()):
                        channel_info = removed_channels[name]
                        message += f'- {name} ({channel_info.number})\n'
                    if name in list(new_channels.keys()):
                        channel_info = new_channels[name]
                        message += f'+ {name} ({channel_info.number})\n'

                if duplicated_channels:
                    message += '\n<--- Duplicated channels --->\n'
                    sorted_names = sorted(list(duplicated_channels.keys()))
                    for name in sorted_names:
                        channel_info_list = duplicated_channels[name]
                        sorted_numbers = sorted([channel_info.number for channel_info in channel_info_list])
                        formatted_numbers = str(sorted_numbers).replace("'", "").replace('[', '').strip(']')
                        message += f'{name}: {formatted_numbers}\n'

    return message

def create_local_file_name(name):
    '''
    If the given name contains spaces, replace them with underscores.
    Prefix the file name with the data directory path.
    The file extension will be ".log"
    '''
    if not name.endswith('.log'):
        name = name + '.log'

    return os.path.join(Data_Subdirectory_Path, name.replace(' ', '_'))

def create_sources(dvr_url):
    '''
    Given the DVR URL, read the raw json list of devices from the Channels DVR server, 
    extract the relevant information and generate a list of sources, which will be instances
    of the ChannelsDVRSource class.
    '''
    devices_url = f'{dvr_url}/devices'
    devices = requests.get(devices_url).json()

    sources = []
    for device in devices:
        if device['Lineup']:
            source = ChannelsDVRSource(device)
            source.current_lineup  = source.get_current_lineup_from_server()
            source.previous_lineup = source.get_previous_lineup_from_file()

            sources.append(source)
    
    return sources

def create_summary_message(dvr_url, sources):
    '''
    Generate a short message that is suitable for a text/SMS.
    It will start with this line: "Channels DVR lineup changes:".
    Then it will list the channel count difference for each modified source.
        
    Example: 
    Channels DVR lineup changes:
    PLEX Live TV: 528 (-2)
    Pluto TV: 373 (+3)
    '''
    message = "Channels DVR lineup changes:\n"
    message += f'({dvr_url})\n'
    
    for source in sources:
        if source.has_lineup_changes():
            channel_count_diff = source.get_channel_count_difference()
            message += f'{source.name}: {len(source.current_lineup)} ({channel_count_diff})\n'    

    return message

def display_header(dvr_url, frequency, sender_address, recipient_address, text_number, log_file):
    '''Print a message on the screen based on the user inputs.'''
    print('')
    print(f'Script version {VERSION}')
    print('')
    print(f'Using Channels DVR server at: {dvr_url}.')
    print(f'Checking for channel lineup changes every {frequency} minutes.')
    print('')
    
    if not sender_address:
        print('Visual monitoring only, no email or text will be sent.')
        print('')
    else:
        if recipient_address:
            print(f'An email will be sent to {recipient_address} when changes are detected.')
            print('')
        if text_number:
            print(f'A text message will be sent to {text_number} when changes are detected.')
            print('')
        
    print(f'Channel lineup changes will be written to:\n{log_file.name}\n')

    print(f'The last activity will be saved in:\n{create_local_file_name(LOG_FILE_ACTIVITY)}\n')  

def get_channels_dvr_version(dvr_url):
    '''
    Retrieve the current version of the Channels DVR server.
    If there is no response from the server, print a message on the screen and return None.
    '''
    status_url = f'{dvr_url}/status'
    dvr_version = None

    try:
        dvr_version = requests.get(status_url).json()['version']
    except:
        print(f'No response from the server at {dvr_url}')
    
    return dvr_version

def get_deleted_sources(sources):
    '''Return a list of source names that are present on the disk and not on the server.'''
    sources_on_disk   = get_source_names_from_disk()
    sources_on_server = [source.name for source in sources]

    deleted_sources = [source_name for source_name in sources_on_disk if source_name not in sources_on_server]

    return deleted_sources

def get_email_provider(sender_address):
    '''Given the email address as user@provider.com, return the provider.'''
    return sender_address.lower().split('@')[1].split('.')[0]

def get_modified_sources(sources):
    '''Return the list of existing sources that have lineup changes.'''
    modified_sources = [source.name for source in sources if source.has_lineup_changes()]

    return modified_sources

def get_new_sources(sources):
    '''Return a list of sources from the server that are not saved on the disk.'''
    sources_on_disk   = get_source_names_from_disk()
    sources_on_server = [source.name for source in sources]

    new_sources = [source_name for source_name in sources_on_server if source_name not in sources_on_disk]

    return new_sources

def get_sorted_channel_names_from_channel_changes(removed_channels, new_channels):
    '''
    Parse the given removed and new channels and return an ordered list of channel names.
    '''
    sorted_names = list(removed_channels.keys())
    sorted_names.extend(list(new_channels.keys()))
    sorted_names.sort()

    return sorted_names

def get_sorted_channel_numbers_from_lineup_changes(deleted_channels, added_channels, modified_channels):
    '''
    Parse all the channel numbers from the given lists of deleted, added, and modified channels.
    Return a list of all these numbers in order.
    '''
    sorted_numbers = list(deleted_channels.keys())
    sorted_numbers.extend(list(added_channels.keys()))
    sorted_numbers.extend(list(modified_channels.keys()))

    sorted_numbers.sort()

    return sorted_numbers

def get_sorted_unique_channel_names_from_lineup(lineup):
    '''
    Extract and return all the channel names from the given lineup.
    In some sources, the same channel may appear more than once.
    Only return unique names.
    '''
    names = []

    for _, channel_info in lineup.items():
        name = channel_info.name

        if not name in names:
            names.append(name)

    return sorted(names)

def get_source_url(dvr_url, source_name):
    '''
    Retrieve the source settings from the server and return the source URL used in the settings.
    '''
    source_name_without_spaces = source_name.replace(' ', '')
    source_settings_url = f'{dvr_url}/providers/m3u/sources/{source_name_without_spaces}'

    try:
        source_settings_json = requests.get(source_settings_url).json()
        source_url = source_settings_json.get('url', None)
    except:
        # In the case of a HDHomeRun or TV Everywhere source, there is no URL
        source_url = None

    return source_url

def get_source_names_from_disk():
    '''Retrieve the names of the sources that are saved on the disk.'''
    all_log_files = [os.path.basename(log_file) for log_file in glob.glob(f'{Data_Subdirectory_Path}/*.log')]
    source_files = [f for f in all_log_files if ((f != LOG_FILE_ACTIVITY) and (LOG_FILE_CHANGES not in f))]
    sources = [os.path.splitext(source_file)[0].replace('_', ' ') for source_file in source_files]

    return sources

def notify_server_offline(dvr_url, sender_address, password, recipient_address, text_number):
    '''If email address and/or text number are/is provided, notify the user that the server is offline.'''
    if sender_address and password:
        subject = f'Channels DVR: no response from {dvr_url}'
        message_body = 'If the URL is correct, it seems that the Channels DVR server is not running.'

        if recipient_address:
            print(f'Sending email to {recipient_address}...')
            send_email(sender_address, password, recipient_address, subject, message_body)
            print('Done')

        if text_number:
            message = subject + '\n'
            message += message_body
            print(f'Sending SMS to {text_number}...')
            send_email(sender_address, password, text_number, '', message)
            print('Done')

def move_deleted_sources(source_names):
    '''Move the deleted sources into a subdirectory.'''
    for name in source_names:
        full_name = create_local_file_name(name)
        move_file_to_subdirectory(full_name, DELETED_SOURCES_DIR)

def move_file_to_subdirectory(file_path, subdir_name):
    # Get the directory of the file
    dir_path = os.path.dirname(file_path)
    
    # Create the subdirectory path
    subdir_path = os.path.join(dir_path, subdir_name)
    
    # Check if the subdirectory does not exist
    if not os.path.exists(subdir_path):
        # Create the subdirectory
        os.makedirs(subdir_path)
    
    # Get the current date in 'YYYY-MM-DD' format
    date_suffix = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    
    # Get the base name of the file (without extension)
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    
    # Get the extension of the file
    extension = os.path.splitext(file_path)[1]
    
    # Create the new file name with the date suffix
    new_file_name = f"{base_name}_{date_suffix}{extension}"
    
    # Create the new file path in the subdirectory
    new_file_path = os.path.join(subdir_path, new_file_name)
    
    # Move the file to the subdirectory
    os.rename(file_path, new_file_path)

def send_email(sender_address, password, recipient_address, subject, message_body):
    '''
    Finish setting up the message for the smtplib library and use smtplib
    to send the email.
    '''
    msg = MIMEText(message_body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From']    = sender_address
    msg['To']      = recipient_address

    send_message(sender_address, password, recipient_address, msg)          

def send_message(sender_address, password, destination, msg):
    '''Send a message from the given email account to the specified destination.'''
    provider = get_email_provider(sender_address)
    smtp_server = SMTP_SERVER_ADDRESS[provider]

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        # Create a secure SSL connection to the SMTP server
        server = smtplib.SMTP(smtp_server, SMTP_PORT)

        # Initiate the SMTP connection
        server.starttls()

        # Login to the email account
        server.login(sender_address, password)

        # Send the email
        server.sendmail(sender_address, [destination], msg.as_string())

    except Exception as e:
        print(f'{current_time} - Error sending message: ' + str(e))

    finally:
        # Close the connection to the SMTP server
        if server:
            server.quit()

def sort_dictionary_keys(dictionary):
    '''Return a sorted list of the keys of the given dictionary.'''
    return sorted(list(dictionary.keys()))

def sources_have_been_modified(sources):
    '''Return True if any of the sources have been modified in any way.'''
    deleted_sources  = get_deleted_sources(sources)
    new_sources      = get_new_sources(sources)
    modified_sources = get_modified_sources(sources)

    return bool(deleted_sources or new_sources or modified_sources)

def update_references(sources):
    '''If any of the given sources have been modified, update the text files that contain their channel lineups.'''
    for source in sources:
        if source.has_lineup_changes() or source.is_new():
            source.save_channel_lineup_to_file()

def write_activity_to_file(message):
    '''Write the given message to the activity file. Overwrite the previous contents.'''
    file_name = create_local_file_name(LOG_FILE_ACTIVITY)

    with open(file_name, 'w') as activity_file:
        activity_file.write(message)


################################################################################
#                                                                              #
#                                 MAIN PROGRAM                                 #
#                                                                              #
################################################################################

if __name__ == "__main__":
    # Create an ArgumentParser object
    parser = argparse.ArgumentParser(
                description = "Monitor a Channels DVR server for changes in channel lineups.",
                epilog = "If no options are specified, use the default URL http://127.0.0.1:8089 " + \
                         "to query the Channels DVR server, and just print information on the screen. " + \
                         "If the -e argument is specified, you must provide at least either -r or -t, or both.")

    # Add the input arguments
    parser.add_argument('-e', '--email_address', type=str, default=None, \
                        help='Email address to use as the sender. Not required if just monitoring on the screen. ' + \
                             'Use with -P, and either -r or -t (or both).')
    parser.add_argument('-f', '--frequency', type=int, default=30, \
                        help='Frequency of queries sent to the Channels DVR server, in minutes. Not required. ' + \
                             'Default: 30. Minimum: 5.')
    parser.add_argument('-i', '--ip_address', type=str, default=LOOPBACK_ADDRESS, \
                        help='IP address of the Channels DVR server. Not required. Default: 127.0.0.1')
    parser.add_argument('-p', '--port_number', type=str, default=DEFAULT_PORT_NUMBER, \
                        help='Port number of the Channels DVR server. Not required. Default: 8089')
    parser.add_argument('-P', '--password', type=str, default=None, \
                        help='Password to log in to the email account. Use with -e.')
    parser.add_argument('-r', '--recipient_address', type=str, default=None, \
                        help='Email address of the recipient. Not required if -t is specified. Use with -e and -P. ' + \
                             'May be the same as -e. May be used with -t too.')
    parser.add_argument('-t', '--text_number', type=str, default=None, \
                        help='Cell phone number to send a text to in the format: <10 digits>@<SMS gateway>. ' + \
                             'Not required if -r is specified. Use with -e and -P. May be used with -r too.')
    parser.add_argument('-v', '--version', action='store_true', help='Print the version number and exit the program.')

    # Parse the arguments
    args = parser.parse_args()

    # Access the values of the arguments
    sender_address    = args.email_address
    frequency         = args.frequency
    ip_address        = args.ip_address
    password          = args.password
    port_number       = args.port_number
    recipient_address = args.recipient_address
    text_number       = args.text_number
    version           = args.version

    # If the version flag is set, print the version number and exit
    if version:
        print(VERSION)
        sys.exit()

    # Sanity check of the provided arguments.
    if sender_address:
        if not password:
            print(f'A password must be specified with -P to log in to the {sender_address} account!')
            sys.exit()
        if not (recipient_address or text_number):
            print('Use the -r and/or the -t option in combination with -e!')
            sys.exit()
            
    if recipient_address and not sender_address:
        print('Use the -e and -P options with -r!')
        sys.exit()
        
    if text_number and not sender_address:
        print('Use the -e and -P options with -t!')
        sys.exit()
        
    if frequency < 5:
        print('Minimum frequency of 5 minutes! Try again.')
        sys.exit()
        
    # All good. Let's go!

    server_is_online = True
    dvr_url = f'http://{ip_address}:{port_number}'

    create_data_subdirectory(ip_address, port_number)

    log_file = LogFile()

    display_header(dvr_url, frequency, sender_address, recipient_address, text_number, log_file)
    
    while server_is_online:
        # Check for changes in the channel lineups in all sources
        server_version = get_channels_dvr_version(dvr_url)

        if server_version:
            current_time = datetime.now()
            next_check_time = current_time + timedelta(minutes=frequency)

            activity_string = 'Check time: ' + current_time.strftime("%Y-%m-%d %H:%M:%S") + '\n\n'

            activity_string += f'Server version: {server_version}\n\n'
            
            sources = create_sources(dvr_url)

            if sources_have_been_modified(sources):
                message = create_detailed_message(dvr_url, server_version, sources)

                log_file.write(message)

                activity_string += message + '\n'
            
                if sender_address:
                    if recipient_address:
                        subject = EMAIL_SUBJECT
                        activity_string += f'Sending email to {recipient_address}... '
                        send_email(sender_address, password, recipient_address, subject, message)
                        activity_string += 'Done\n'
                        
                    if text_number:
                        subject = ''
                        message = create_summary_message(dvr_url, sources)
                        activity_string += f'Sending SMS to {text_number}... '
                        send_email(sender_address, password, text_number, subject, message)
                        activity_string += 'Done\n'

                update_references(sources)

            else:
                activity_string += 'No changes found in any source.\n'
            
            activity_string += '\nNext check: ' + next_check_time.strftime("%Y-%m-%d %H:%M:%S") + '\n'

            write_activity_to_file(activity_string)

            move_deleted_sources(get_deleted_sources(sources))

            time.sleep(frequency * 60)
        else:
            print('If the URL is correct, the server is offline.')
            print('')
            notify_server_offline(dvr_url, sender_address, password, recipient_address, text_number)
            server_is_online = False
