# Channels DVR Monitor Channel Lineups
 Send notifications when channel lineups change on a Channels DVR server
 
 Script usage:
 
 1. Display the help text:
 
 > python channels_dvr_monitor_channels.py -h
 
 usage: channels_dvr_monitor_channels.py [-h] [-e EMAIL_ADDRESS] [-f FREQUENCY] [-i IP_ADDRESS] [-p PORT_NUMBER]
                                         [-P PASSWORD] [-r RECIPIENT_ADDRESS] [-t TEXT_NUMBER] [-v]

Monitor a Channels DVR server for changes in channel lineups.

options:
  -h, --help            show this help message and exit
  -e EMAIL_ADDRESS, --email_address EMAIL_ADDRESS
                        Email address to use as the sender. Not required if just monitoring on the screen. Use with
                        -P, and either -r or -t (or both).
  -f FREQUENCY, --frequency FREQUENCY
                        Frequency of queries sent to the Channels DVR server, in minutes. Not required. Default: 30.
                        Minimum: 5.
  -i IP_ADDRESS, --ip_address IP_ADDRESS
                        IP address of the Channels DVR server. Not required. Default: 127.0.0.1
  -p PORT_NUMBER, --port_number PORT_NUMBER
                        Port number of the Channels DVR server. Not required. Default: 8089
  -P PASSWORD, --password PASSWORD
                        Password to log in to the email account. Use with -e.
  -r RECIPIENT_ADDRESS, --recipient_address RECIPIENT_ADDRESS
                        Email address of the recipient. Not required if -t is specified. Use with -e and -P. May be
                        the same as -e. May be used with -t too.
  -t TEXT_NUMBER, --text_number TEXT_NUMBER
                        Cell phone number to send a text to in the format: <10 digits>@<SMS gateway>. Not required if
                        -r is specified. Use with -e and -P. May be used with -r too.
  -v, --version         Print the version number and exit the program.

If no options are specified, use the default URL http://127.0.0.1:8089 to query the Channels DVR server, and just
print information on the screen. If the -e argument is specified, you must provide at least either -r or -t, or both.
 
---

2. Run the script on the same machine that is running Channels DVR and choose to do visual monitoring only, no notifications, at the default frequency of 30 minutes:

>  python channels_dvr_monitor_channels.py

Using Channels DVR URL: http://127.0.0.1:8089/devices.
Checking for channel lineup changes every 30 minutes.

Visual monitoring only, no email or text will be sent.

Last check: 2023-05-26 23:53:53
added channels   : {}
modified channels: {}
removed channels : {}

Next check: 2023-05-27 00:23:53

---

3. Same thing but check for changes every 15 minutes:

> python channels_dvr_monitor_channels.py -f 15

Using Channels DVR URL: http://127.0.0.1:8089/devices.
Checking for channel lineup changes every 15 minutes.

Visual monitoring only, no email or text will be sent.

Last check: 2023-05-26 23:56:50
added channels   : {}
modified channels: {}
removed channels : {}

Next check: 2023-05-27 00:11:50

---

4. Now the Channels DVR is running on a different machine and its IP address is 192.168.0.155, use the default port number:

> python channels_dvr_monitor_channels.py -f 15 -i 192.168.0.155

Using Channels DVR URL: http://192.168.0.155:8089/devices.
Checking for channel lineup changes every 15 minutes.

Visual monitoring only, no email or text will be sent.

Last check: 2023-05-26 23:59:05
added channels   : {}
modified channels: {}
removed channels : {}

Next check: 2023-05-27 00:14:05

---

5. Back to defaults but now add email notifications:

> python channels_dvr_monitor_channels.py -e EMAIL_ADDRESS -P PASSWORD -r RECIPIENT_ADDRESS

Using Channels DVR URL: http://127.0.0.1:8089/devices.
Checking for channel lineup changes every 30 minutes.

An email will be sent to RECIPIENT_ADDRESS when changes are detected.

Last check: 2023-05-27 00:02:16
added channels   : {}
modified channels: {}
removed channels : {}

Next check: 2023-05-27 00:32:16

*** Notes:

EMAIL_ADDRESS = address of the email account that will be used to send the email

PASSWORD = the password to log in to that email account. In the case of Yahoo! Mail and Gmail, you will have to create an app password to be used exclusively by this script. If using Outlook.com, the normal account password will work.

RECIPIENT_ADDRESS = email address where to send the email to. It can be the same as EMAIL_ADDRESS (send email to yourself)

---

6. You can add text notification:

> python channels_dvr_monitor_channels.py -e EMAIL_ADDRESS -P PASSWORD -r RECIPIENT_ADDRESS -t NUMBER@SMS_GATEWAY

Using Channels DVR URL: http://127.0.0.1:8089/devices.
Checking for channel lineup changes every 30 minutes.

An email will be sent to EMAIL_ADDRESS when changes are detected.
A text message will be sent to NUMBER@SMS_GATEWAY when changes are detected.

Last check: 2023-05-27 00:12:59
added channels   : {}
modified channels: {}
removed channels : {}

Next check: 2023-05-27 00:42:59

*** Notes:

NUMBER = 10 digits of cell phone number
SMS_GATEWAY = see https://en.wikipedia.org/wiki/SMS_gateway for the SMS gateway used by your cell phone carrier

EMAIL_ADDRESS from Yahoo! Mail has been tested successfully to send text messages to a Verizon number.
EMAIL_ADDRESS from Outlook.com: text messages are very delayed in my tests (more than 12 hours!) so not recommended

A Gmail account has NOT been tested at all as the sender of either emails or text messages, but support for it is present in the script. 
 

