# Channels DVR Monitor Channel Lineups
 Send notifications when channel lineups change on a Channels DVR server
 
 Script usage:
 
 1. Display the help text:
 
 > python channels_dvr_monitor_channels.py -h
 
---

2. Run the script on the same machine that is running Channels DVR and choose to do visual monitoring only, no notifications, at the default frequency of 30 minutes:

>  python channels_dvr_monitor_channels.py

---

3. Same thing but check for changes every 15 minutes:

> python channels_dvr_monitor_channels.py -f 15

---

4. Now the Channels DVR is running on a different machine and its IP address is 192.168.0.155, use the default port number:

> python channels_dvr_monitor_channels.py -f 15 -i 192.168.0.155

---

5. Back to defaults but now add email notifications:

> python channels_dvr_monitor_channels.py -e EMAIL_ADDRESS -P PASSWORD -r RECIPIENT_ADDRESS

*** Notes:

EMAIL_ADDRESS = address of the email account that will be used to send the email

PASSWORD = the password to log in to that email account. In the case of Yahoo! Mail and Gmail, you will have to create an app password to be used exclusively by this script. If using Outlook.com, the normal account password will work.

RECIPIENT_ADDRESS = email address where to send the email to. It can be the same as EMAIL_ADDRESS (send email to yourself)

---

6. You can add text notification:

> python channels_dvr_monitor_channels.py -e EMAIL_ADDRESS -P PASSWORD -r RECIPIENT_ADDRESS -t NUMBER@SMS_GATEWAY

*** Notes:

NUMBER = 10 digits of cell phone number

SMS_GATEWAY = see https://en.wikipedia.org/wiki/SMS_gateway for the SMS gateway used by your cell phone carrier

EMAIL_ADDRESS from Yahoo! Mail has been tested successfully to send text messages to a Verizon number.
EMAIL_ADDRESS from Outlook.com: text messages are very delayed in my tests (more than 12 hours!) so not recommended

A Gmail account has NOT been tested at all as the sender of either emails or text messages, but support for it is present in the script. 
 

