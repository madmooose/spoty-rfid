Spoty-rfid
==========

aka Kühniebox aka spoty-box At some point I need a better name. 

This is a simple hacky rfid-box to trigger any spotify-player (incl. [Raspotify](https://gist.github.com/sonicdee/bf5f655669ef6900b72c54f0c7696d32). It's build with raspberry pi in mind.

At the moment it can only trigger playlists on a specific device. More commands will eventually follow.

Work is based on https://gist.github.com/sonicdee/bf5f655669ef6900b72c54f0c7696d32

### clone to home-directory

```sh
   git clone https://github.com/madmooose/spoty-rfid
```
and install all requirements.
```sh
   sudo apt-get install python3-pip
   sudo pip install spotipy
```

### Create a cards.txt
Format is like that
```txt
[number of rfid-tag] [spotify-uri] # here's some space for comments
```

### Create udev-rule to own the rfid-reader
Run
```sh 
  lsusb
```
and remember both numbers behind ID. In `/etc/udev/rules.d` create a file called `50-usb-rfidreader.rules` and and the following line
```txt
   SUBSYSTEMS=="usb", ATTRS{idVendor}=="[numer1]", ATTRS{idProduct}=="[number2]", MODE="0666"
```

Now reload udev.
```sh
   sudo udevadm control --reload-rules
   sudo udevadm trigger
```
Check if you have read-and-write-access.
```sh
   ls -l /dev/usb/hidraw0
```

### Configure the spotify
Visit [Spotify Devoloper Dashboard](https://developer.spotify.com/dashboard/applications) and create an app. Remember `Client ID` and `Client Secret`. Also edit settings and add `http://localhost:8080` to `Redirect URIs`.
Now switch to the cosole-tab on the Developer Dashboard and choose `Player`. Click on `/v1/me/player/devices`, `get token` (user-read-playback-state is enough) and `try it`. Grab the ID of the client you what to control.

Now you have to add the collected values to `spotycon.py`.

We will now run
```sh
   ./RfSpoty.py
```
for the first time to create the `.cache` file where the access token is stored. You have to follow the URL and paste the URL of your browser back into your command line.

Now theres another hack we have to do. In order to no loose connection to our spotify client, we have to check if its still avaible and restart it if not. Add the following to your crontab as root.
```sh
   sudo crontab -e
```
and add
```txt
0 3 * * * /home/pi/spotify-rfid/awake_librespot.py
```



### Daemonize it

Copy `spoty-rfid.service` to `/etc/system.d/system/` and activate it
```sh
  sudo cp spoty-rfid.service /etc/system.d/system
  sudo systemctl enable spoty-rfid
  sudo systemctl start spoty-rfid
```
