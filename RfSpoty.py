#!/usr/bin/env python3

import sys

#A) install raspotify
#sudo apt-get -y install curl && curl -sL https://dtcooper.github.io/raspotify/install.sh | sh
#you need to edit the config: sudo nano /etc/raspotify/conf
#change LIBRESPOT_NAME to your whatever you like
#you must add LIBRESPOT_USERNAME and PASSWORD otherwise the device won't be found from spotipy on reboot of the Box

#B)pip and spotipy:
#sudo apt-get install python3-pip
#sudo pip install spotipy

#sudo apt-get install screen

#C)screen sudo RfSpoty.py
#Ctrl+a d -> to detach

#D)screen sudo Gpio.py
#Ctrl+a d -> to detach

import spotycon

#!! uncomment below -> connection for the frist time, give access to app !browser needed!, and enter aiming deviceID !!
#spotycon.connect_firstauth()
#!! you can then copy over .cache to your headless device

def rfidusb():
    print("start async rfidreader")
    #rfidusb
    fp = open('/dev/usb/hiddev0', 'rb')
    newCode = ''
    while True:
        buffer = fp.read(1)
        for c in buffer:

            if c > 0:
                if c == 30 : newCode = newCode + '1'
                elif c == 31 : newCode = newCode + '2'
                elif c == 32 : newCode = newCode + '3'
                elif c == 33 : newCode = newCode + '4'
                elif c == 34 : newCode = newCode + '5'
                elif c == 35 : newCode = newCode + '6'
                elif c == 36 : newCode = newCode + '7'
                elif c == 37 : newCode = newCode + '8'
                elif c == 38 : newCode = newCode + '9'
                elif c == 39 : newCode = newCode + '0'
                elif c == 40 :
                    #print('code:' + newCode)
                    rfID = str(newCode[::2]) # [::2] -> remove every second char
                    if(len(rfID) > 0):
                        print(rfID)
                        spotycon.playcard(rfID)
                    # reset code
                    newCode = ''

rfidusb()
