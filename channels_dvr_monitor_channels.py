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
"""

################################################################################
#                                                                              #
#                                   IMPORTS                                    #
#                                                                              #
################################################################################

import argparse, json, os, requests, smtplib, sys, time

from datetime import datetime, timedelta
from email.mime.text import MIMEText

################################################################################
#                                                                              #
#                                  CONSTANTS                                   #
#                                                                              #
################################################################################

DEFAULT_PORT_NUMBER  = '8089'
EMAIL_SUBJECT        = 'Channels DVR: changes in channel lineups'
LOG_FILE             = "cdvr_channel_lineup_changes.txt"
LOOPBACK_ADDRESS     = '127.0.0.1'
SEPARATOR_CHARACTER  = '='
SMTP_PORT            = 587
SMTP_SERVER_ADDRESS  = {
                        'gmail'  : 'smtp.gmail.com', 
                        'outlook': 'smtp-mail.outlook.com', 
                        'yahoo'  : 'smtp.mail.yahoo.com'
                       }
VERSION              = '2.0.0'

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
    def __init__(self, source):
        '''Initialize the attributes of this source.'''
        self.source = source
        self.name = self.source['FriendlyName']
        self.current_lineup  = self.get_current_lineup_from_server()
        self.previous_lineup = self.get_previous_lineup_from_file()

    def delete_lineup_file(self):
        '''
        Delete the text file that contains the channel lineup of this source.
        '''
        file_name = self.name + '.txt'

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
        file_name = self.name + '.txt'

        if os.path.exists(file_name):
            with open(file_name) as txt_file:
                lines = txt_file.read().splitlines()

            for line in lines:
                channel_json = {}

                channel_number = line.split(SEPARATOR_CHARACTER)[0]
                channel_name   = line.split(SEPARATOR_CHARACTER)[1]
                channel_id     = line.split(SEPARATOR_CHARACTER)[2]

                channel_json['ID']          = channel_id
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

    def is_new(self):
        '''
        Return a boolean: True when there is no existing channel lineup text file for this source.
        '''
        is_source_new = not os.path.exists(self.name + '.txt')

        return is_source_new

    def save_channel_lineup_to_file(self):
        '''
        Replace the content of the text file that contains the channel lineup of this source
        with the current channel lineup.
        '''
        self.delete_lineup_file()

        with open(self.name + '.txt', 'a') as txt_file:
            sorted_channel_numbers = sort_dictionary_keys(self.current_lineup)

            for channel_number in sorted_channel_numbers:
                channel_info = self.current_lineup[channel_number]
                channel_name = channel_info.name
                channel_id   = channel_info.id
                line_to_write = f'{channel_number}{SEPARATOR_CHARACTER}{channel_name}{SEPARATOR_CHARACTER}{channel_id}\n'
                txt_file.write(line_to_write)

################################################################################
#                                                                              #
#                                  FUNCTIONS                                   #
#                                                                              #
################################################################################

def create_detailed_message(server_version, sources):
    '''
    Generate a string that is easy to read in an email.
    It will start with the version of the Channels DVR server.
    Then it will list the removed channels, added channels, and modified
    channels for each source as follows:
    
        Source name:
        - channel number : name of removed channel 1
        - channel number : name of removed channel 2
        - ...
        - channel number : name of removed channel N
        + channel number : name of added channel 1
        + channel number : name of added channel 2
        + ...
        + channel number : name of added channel N
        ! channel number : old channel name -> new channel name
        ! ...
        ! channel number : old channel name -> new channel name
        
    Bonus: when pasting this message as is in the Channels DVR forum and choosing
    the formatted text option, the removed channels are automatically highlighted 
    in red, and the added channels in green.
    
    For each source that was modified, the new channel count will also be shown
    with the channel count difference in parenthesis compared to the last count.
    Example:
        "Pluto TV channel count: 358 (-2)"    
    '''
    message = f'Channels DVR version: {server_version}\n'
    
    for source in sources:
        if source.is_new():
            message += '\n'
            number_of_channels = len(source.current_lineup)
            message += f'New source with {number_of_channels} channels: {source.name}\n'
            if number_of_channels:
                message += f'See file {source.name}.txt for the full lineup.\n'
        else:
            if source.has_lineup_changes():
                deleted_channels  = source.get_deleted_channel_numbers()
                added_channels    = source.get_added_channel_numbers()
                modified_channels = source.get_modified_channels()
                removed_channels  = source.get_removed_channel_names()
                new_channels      = source.get_new_channel_names()

                message += '\n'
                channel_count_diff = source.get_channel_count_difference()
                message += f'{source.name}: {len(source.current_lineup)} channels ({channel_count_diff})\n'

                if removed_channels or new_channels:
                    message += '------ Lineup changes ------\n'
                
                if deleted_channels:
                    sorted_numbers = sort_dictionary_keys(deleted_channels)
                    for number in sorted_numbers:
                        channel_info = deleted_channels[number]
                        message += f'- {number} : {channel_info.name} ({channel_info.id})\n'
                    
                if added_channels:
                    sorted_numbers = sort_dictionary_keys(added_channels)
                    for number in sorted_numbers:
                        channel_info = added_channels[number]
                        message += f'+ {number} : {channel_info.name} ({channel_info.id})\n'

                if modified_channels:
                    sorted_numbers = sort_dictionary_keys(modified_channels)
                    for number in sorted_numbers:
                        old_channel_info = modified_channels[number][0]
                        new_channel_info = modified_channels[number][1]
                        message += f'! {number} : {old_channel_info.name} ({old_channel_info.id}) -> {new_channel_info.name} ({new_channel_info.id})\n'
                    
                if removed_channels or new_channels:
                    message += '------ Channel changes ------\n'
                
                if removed_channels:
                    sorted_names = sort_dictionary_keys(removed_channels)
                    for name in sorted_names:
                        channel_info = removed_channels[name]
                        message += f'- {name} ({channel_info.id}) [{channel_info.number}]\n'
                
                if new_channels:
                    sorted_names = sort_dictionary_keys(new_channels)
                    for name in sorted_names:
                        channel_info = new_channels[name]
                        message += f'+ {name} ({channel_info.id}) [{channel_info.number}]\n'

    return message
    
def create_sources(dvr_url):
    '''
    Given the raw json list of devices from the Channels DVR server, extract the
    relevant information and generate a list of sources, which will be instances
    of the ChannelsDVRSource class.
    '''
    devices_url = f'{dvr_url}/devices'
    devices = requests.get(devices_url).json()
    
    return [ChannelsDVRSource(device) for device in devices]
    
def create_summary_message(sources):
    '''
    Generate a short message that is suitable for a text/SMS.
    It will list the removed channel numbers and added channel numbers 
    for each source as follows:
    
        Source name: number of channels (channel count difference)
        
        Example: Pluto TV: 373 (+3)
    '''
    message = ""
    
    for source in sources:
        if source.has_lineup_changes():
            channel_count_diff = source.get_channel_count_difference()
            message += f'{source.name}: {len(source.current_lineup)} ({channel_count_diff})\n'    

    return message

def display_header(dvr_url, frequency, log_changes, sender_address, recipient_address, text_number):
    '''Print a message on the screen based on the user inputs.'''
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
        
    if log_changes:
        print(f'Changes will be written to log file {LOG_FILE}.')
        print('')        

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

def get_email_provider(sender_address):
    '''Given the email address as user@provider.com, return the provider.'''
    return sender_address.lower().split('@')[1].split('.')[0]

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

    names.sort()

    return names

def notify_server_offline(dvr_url, sender_address, password, recipient_address, text_number):
    '''If email address and/or text number are/is provided, notify the user that the server is offline.'''
    if sender_address and password:
        subject = f'Channels DVR: no response from {dvr_url}'
        message_body = 'If the URL is correct, it seems that the Channels DVR server is not running.'

        if recipient_address:
            print(f'Sending email to {recipient_address}...')
            send_email(sender_address, password, recipient_address, subject, message_body)

        if text_number:
            message = subject + '\n'
            message += message_body
            print(f'Sending SMS to {text_number}...')
            send_email(sender_address, password, text_number, '', message)

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
    
    try:
        # Create a secure SSL connection to the SMTP server
        server = smtplib.SMTP(smtp_server, SMTP_PORT)

        # Initiate the SMTP connection
        server.starttls()

        # Login to the email account
        server.login(sender_address, password)

        # Send the email
        server.sendmail(sender_address, [destination], msg.as_string())

        print('Message sent successfully!')
        print('')

    except Exception as e:
        print('Error sending message:', str(e))

    finally:
        # Close the connection to the SMTP server
        server.quit()

def sort_dictionary_keys(dictionary):
    '''Return a sorted list of the keys of the given dictionary.'''
    sorted_keys = list(dictionary.keys())
    sorted_keys.sort()

    return sorted_keys

def sources_have_been_modified(sources):
    '''Return True if any of the given sources have been modified in any way.'''
    return any([source.has_lineup_changes() for source in sources])

def update_references(sources):
    '''If any of the given sources have been modified, update the text files that contain their channel lineups.'''
    for source in sources:
        if source.has_lineup_changes():
            source.save_channel_lineup_to_file()

def write_to_log_file(timestamp, message):
    '''Write the given message to the log file.'''
    string_to_write = '\n-------------------------------------\n\n'
    string_to_write += timestamp.strftime("%Y-%m-%d %H:%M:%S") + '\n'
    string_to_write += message

    with open(LOG_FILE, 'a') as log_file:
        log_file.write(string_to_write)

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
    parser.add_argument('-l', '--log', action='store_true', help='Log channel changes to a file.')
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
    log_changes       = args.log
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

    display_header(dvr_url, frequency, log_changes, sender_address, recipient_address, text_number)
    
    while server_is_online:
        # Check for changes in the channel lineups in all sources
        server_version = get_channels_dvr_version(dvr_url)

        if server_version:
            current_time = datetime.now()
            next_check_time = current_time + timedelta(minutes=frequency)
            print( 'Last check    :', current_time.strftime("%Y-%m-%d %H:%M:%S"))
            print(f'Server version: {server_version}')
            
            sources = create_sources(dvr_url)
        
            if sources_have_been_modified(sources):
                print('')

                message = create_detailed_message(server_version, sources)

                print(message)
                
                if log_changes:
                    write_to_log_file(current_time, message)
            
                if sender_address:
                    if recipient_address:
                        subject = EMAIL_SUBJECT
                        print(f'Sending email to {recipient_address}...')
                        send_email(sender_address, password, recipient_address, subject, message)
                        
                    if text_number:
                        subject = ''
                        message = create_summary_message(sources)
                        print(f'Sending SMS to {text_number}...')
                        send_email(sender_address, password, text_number, subject, message)

                update_references(sources)

            else:
                print('No changes found in any source.')
            
            print('Next check:', next_check_time.strftime("%Y-%m-%d %H:%M:%S"))
            print('')

            time.sleep(frequency * 60)
        else:
            print('If the URL is correct, the server is offline.')
            print('')
            notify_server_offline(dvr_url, sender_address, password, recipient_address, text_number)
            server_is_online = False
