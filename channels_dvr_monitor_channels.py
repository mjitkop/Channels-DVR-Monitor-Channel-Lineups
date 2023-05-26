"""
Author: Gildas Lefur (a.k.a. "mjitkop" in the Channels DVR forums)

Description: This script monitors the channel lineups in a Channels DVR server.
             If changes are detected, it may send an email and/or text message
             as specified in the input arguments.

Disclaimer: this is an unofficial script that is NOT supported by the developers
            of Channels DVR.

For bug reports and support, go to: 
https://community.getchannels.com/t/python-script-to-be-notified-of-channel-changes/36464?u=mjitkop

Version History:
- 2023.05.25.2348: Initial version of the script.
"""

################################################################################
#                                                                              #
#                                   IMPORTS                                    #
#                                                                              #
################################################################################

import argparse, json, requests, smtplib, sys, time

from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

################################################################################
#                                                                              #
#                                  CONSTANTS                                   #
#                                                                              #
################################################################################

DEFAULT_PORT_NUMBER = '8089'
EMAIL_SUBJECT       = 'Channels DVR: changes in channel lineups'
LOOPBACK_ADDRESS    = '127.0.0.1'
SMTP_PORT           = 587
SMTP_SERVER_ADDRESS = {
                        'gmail'  : 'smtp.gmail.com', 
                        'outlook': 'smtp-mail.outlook.com', 
                        'yahoo'  : 'smtp.mail.yahoo.com'
                      }
TEXT_SUBJECT        = 'Channels'
VERSION             = '2023.05.25.2348'

################################################################################
#                                                                              #
#                                   CLASSES                                    #
#                                                                              #
################################################################################

class ChannelsDVRSource:
    '''Attributes and methods to handle one channel source.'''
    def __init__(self, source):
        self.source = source
        self.name = self.source['FriendlyName']
        self.current_channels  = self._get_current_channels()
        self.previous_channels = self.current_channels
        self.added_channels    = {}
        self.removed_channels  = {}
        self.modified_channels = {}

    def _get_current_channels(self):
        '''Extract the channels from the provided source.'''
        current_channels = {}

        for channel in self.source['Channels']:
            number = channel['GuideNumber']
            name   = channel['GuideName']
            current_channels[number] = name

        return current_channels

    def _get_added_channels(self):
        '''
        Compare the previous and current channel lineups and return the 
        new channels that only appear in the current lineup.
        '''
        added_channels = {}

        previous_set = set(self.previous_channels)
        current_set  = set(self.current_channels)
        new_channel_numbers = list(current_set.difference(previous_set))
        
        for number in new_channel_numbers:
            added_channels[number] = self.current_channels[number]

        return added_channels

    def _get_removed_channels(self):
        '''
        Compare the previous and current channel lineups and return the 
        channels that only appear in the previous lineup.
        '''
        removed_channels = {}
        
        previous_set = set(self.previous_channels)
        current_set  = set(self.current_channels)
        removed_channel_numbers = list(previous_set.difference(current_set))
        
        for number in removed_channel_numbers:
            removed_channels[number] = self.previous_channels[number]

        return removed_channels

    def _get_modified_channels(self):
        '''
        Compare the channel numbers and channel names in the previous
        channels and the current channels. Return the list of channels
        whose names are different for the same channel numbers.
        '''
        modified_channels = {}

        for channel_number, previous_name in self.previous_channels.items():
            current_name = self.current_channels.get(channel_number, None)
            if current_name and current_name != previous_name:
                modified_channels[channel_number] = (previous_name, current_name)

        return modified_channels
        
    def update(self, device):
        '''
        Given the updated current channels retrieved from the Channels DVR server
        (in device), update all internal attributes accordingly.
        '''
        self.source = device
        self.current_channels  = self._get_current_channels()
        self.added_channels    = self._get_added_channels()
        self.modified_channels = self._get_modified_channels()
        self.removed_channels  = self._get_removed_channels()
        self.previous_channels = self.current_channels

################################################################################
#                                                                              #
#                                  FUNCTIONS                                   #
#                                                                              #
################################################################################

def create_sources(devices):
    '''
    Given the raw json list of devices from the Channels DVR server, extract the
    relevant information and generate a list of sources, which will be instances
    of the ChannelsDVRSource class.
    '''
    return [ChannelsDVRSource(device) for device in devices]

def format_message_for_email(added_channels, modified_channels, removed_channels):
    '''Generate a string that is easy to read in an email.'''
    message = ""
    
    if added_channels:
        message += "------ New channels ------\n\n"
        
        for source_name, channels in added_channels.items():
            message += f'{source_name}\n'
            sorted_numbers = list(channels.keys())
            sorted_numbers.sort()
            
            for number in sorted_numbers:
                name = channels[number]
                message += f'    {number} : {name}\n'
                
            message += '\n'
            
    if modified_channels:
        message += "------ Modified channels ------\n\n"
        
        for source_name, channels in modified_channels.items():
            message += f'{source_name}\n'
            sorted_numbers = list(channels.keys())
            sorted_numbers.sort()
            
            for number in sorted_numbers:
                previous_name = channels[number][0]
                new_name      = channels[number][1]
                message += f'    {number} : {previous_name} -> {new_name}\n'
                
            message += '\n'
        
    if removed_channels:
        message += "------ Removed channels ------\n\n"
        
        for source_name, channels in removed_channels.items():
            message += f'{source_name}\n'
            sorted_numbers = list(channels.keys())
            sorted_numbers.sort()
            
            for number in sorted_numbers:
                name = channels[number]
                message += f'    {number} : {name}\n'
                
            message += '\n'
            
    return message

def format_message_for_sms(added_channels, modified_channels, removed_channels):
    '''Generate a short message that is suitable for a text/SMS'''
    message = ""
    
    if added_channels:
        message += "*New* "
        message = add_numbers_to_sms_message_and_return(message, added_channels)
            
    if modified_channels:
        message += "\n*Changed* "
        message = add_numbers_to_sms_message_and_return(message, modified_channels)
        
    if removed_channels:
        message += "\n*Removed* "
        message = add_numbers_to_sms_message_and_return(message, removed_channels)
            
    return message
    
def add_numbers_to_sms_message_and_return(message, channel_list):
    '''
    Parse the channel list and add source name + list of numbers to the message.
    Return the message when done.
    '''
    for source_name, channels in channel_list.items():
        source_name = source_name.split(' ')[0] # Only keep the first word
        message += f'{source_name}: '
        sorted_numbers = list(channels.keys())
        sorted_numbers.sort()
        
        for number in sorted_numbers:
            message += f'{number}, '
            
        # Remove the last comma and space
        message = message[:-2]
        
        message += ' '
    
    return message

def get_email_provider(sender_address):
    '''Given the email address as user@provider.com, return the provider.'''
    return sender_address.lower().split('@')[1].split('.')[0]
    
def get_message_type(destination):
    '''
    Based on the given destination address, determine whether the message
    to be sent is an email or a text message.
    '''
    provider = get_email_provider(destination)
    
    type = 'an email'
    if not provider in SMTP_SERVER_ADDRESS.keys():
        type = 'a text'
        
    return type

def send_message(sender_address, password, subject, destination, message):
    '''Send a message from the given email account to the specified destination.'''
    message_type = get_message_type(destination)
    provider = get_email_provider(sender_address)

    print(f'Sending {message_type} to {destination}...')
    
    smtp_server = SMTP_SERVER_ADDRESS[provider]
    
    # Create a multipart message
    msg = MIMEMultipart()
    msg['From'] = sender_address
    msg['To'] = destination
    msg['Subject'] = subject

    # Attach the message to the MIMEMultipart object
    msg.attach(MIMEText(message, 'plain'))
    
    try:
        # Create a secure SSL connection to the SMTP server
        server = smtplib.SMTP(smtp_server, SMTP_PORT)

        # Initiate the SMTP connection
        server.starttls()

        # Login to the email account
        server.login(sender_address, password)

        # Send the email
        server.sendmail(sender_address, destination, msg.as_string())

        print('Message sent successfully!')
        print('')

    except Exception as e:
        print('Error sending message:', str(e))

    finally:
        # Close the connection to the SMTP server
        server.quit()
    

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
            print('Use the -r and/or the -t option with -e!')
            sys.exit()
            
    if recipient_address and not sender_address:
        print('Use the -e option with -r!')
        sys.exit()
        
    if text_number and not sender_address:
        print('Use the -e option with -t!')
        sys.exit()
        
    if frequency < 5:
        print('Minimum frequency of 5 minutes! Try again.')
        sys.exit()
        
    # All good. Let's go!

    server_url = f'http://{ip_address}:{port_number}/devices'
    print('')
    print(f'Using Channels DVR URL: {server_url}.')
    print(f'Checking for channel lineup changes every {frequency} minutes.')
    print('')
    
    if not sender_address:
        print('Visual monitoring only, no email or text will be sent.')
    else:
        email_provider = get_email_provider(sender_address)
        smtp_server_address = SMTP_SERVER_ADDRESS[email_provider]
        
        if recipient_address:
            print(f'An email will be sent to {recipient_address} when changes are detected.')
        if text_number:
            print(f'A text message will be sent to {text_number} when changes are detected.')
    print('')        
    
    # Retrieve information about the sources from the Channels DVR server
    sources = create_sources(requests.get(server_url).json())
    
    while True:
        # Check for changes in the channel lineups in all sources
        added_channels    = {}
        modified_channels = {}
        removed_channels  = {}
        
        # Get the current list of devices from the Channels DVR server
        devices = requests.get(server_url).json()

        # Update the sources with this newly retrieved list of devices, and
        # generate the list of added, modified, and removed channels.
        for source in sources:
            for device in devices:
                if device['FriendlyName'] == source.name:
                    break
                    
            source.update(device)
            
            if source.added_channels:
                added_channels[source.name] = source.added_channels
            if source.modified_channels:
                modified_channels[source.name] = source.modified_channels
            if source.removed_channels:
                removed_channels[source.name] = source.removed_channels

        current_time = datetime.now()
        next_check_time = current_time + timedelta(minutes=frequency)
        print("Last check:", current_time.strftime("%Y-%m-%d %H:%M:%S"))
        print(f'added channels   : {added_channels}')
        print(f'modified channels: {modified_channels}')
        print(f'removed channels : {removed_channels}')
        print('')
        
        if sender_address and (added_channels or modified_channels or removed_channels):
            if recipient_address:
                message = format_message_for_email(added_channels, modified_channels, removed_channels)
                send_message(sender_address, password, EMAIL_SUBJECT, recipient_address, message)
                
            if text_number:
                message = format_message_for_sms(added_channels, modified_channels, removed_channels)
                send_message(sender_address, password, TEXT_SUBJECT, text_number, message)
        
        print("Next check:", next_check_time.strftime("%Y-%m-%d %H:%M:%S"))
        print('')
        
        time.sleep(frequency * 60)