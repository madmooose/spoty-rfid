import spotipy
import subprocess
import time
from spotipy.oauth2 import SpotifyOAuth
import config
import logging

logging.basicConfig(filename='spotyCon.log', format='%(asctime)s %(message)s', level=logging.DEBUG)

#match this with libresport default volume inside CONF
volumecurrent = 60

# 1) a app must be created, write down keys to config.py
# https://developer.spotify.com/dashboard/applications

# 2) !give your app access once using a -non headless- machine, it will open a webbrowser!
# ->run connect_firstauth() from RfSpoty
# if you need auth for another user, there is a .cache in the .py folder -> just delete it 
# -> copy over to your headless machine

CLIENT_ID: str = config.CLIENT_ID
CLIENT_SECRET: str = config.CLIENT_SECRET
REDIRECT_URI: str = config.REDIRECT_URI

# 3) Get device it from Developer Console and put it in config.py

DEVICE_ID = config.DEVICE_ID
SCOPE = "user-read-playback-state,user-modify-playback-state"

def connect_firstauth():
    # connect to spotify app and auth with browser
    sp = spotipy.Spotify(client_credentials_manager=SpotifyOAuth(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI, scope=SCOPE,open_browser=True))

    return sp

def connect():
    sp = spotipy.Spotify(client_credentials_manager=SpotifyOAuth(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI, scope=SCOPE,open_browser=False))
    return sp

def transfer_to_box():
    spc = connect()
    spc.transfer_playback(device_id=DEVICE_ID, force_play=true)

def restart_box():
    logging.info("Device inactive or hijacked: Restarting librespot")
    subprocess.run(["sudo", "systemctl", "restart", "raspotify"])
    time.sleep(3) # wait till process is actually there
    logging.info("done")
   

def is_active(spc):
    devices = spc.devices()['devices']
    for device in devices:
        if device['is_active'] == True:
            return True
    return False

def box_is_active(spc):
    devices = spc.devices()['devices']
    for device in devices:
        #logging.debug('Device ID: ' + device['id'])
        if (device['id'] == DEVICE_ID):
            logging.info('Device is active')
            return True
    restart_box()
    return False

def card_react(cardID):

    # get dict (getting it late -> you can make changes anytime)
    d = {}
    with open("cards.txt") as f:
        for line in f:
            ll = line.split(" #")[0] # comments so you can write down the Album/Playlist name
            (key, val) = ll.split()
            d[key] = val

    if cardID in d.keys():
        print(d[cardID])
        if d[cardID] == "play":
            btn_play()
        elif d[cardID] == "pause":
            btn_pause()
        elif d[cardID] == "playpause":
            btn_toggleplay()
        elif d[cardID] == "next":
            btn_tracknext()
        elif d[cardID] == "prev":
            btn_trackprev()
        elif d[cardID] == "volUp":
            btn_volUp()
        elif d[cardID] == "volDown":
            btn_volDown()
        elif d[cardID] == "transfer":
            transfer_to_box()
        else:
            do_play(d[cardID])
    else:
        logging.warning("Add {!r} to your cards.txt".format(cardID))

def do_play(spotify_uri):
    spc = connect()
    if is_active(spc):
        spc.start_playback(context_uri=spotify_uri)
    else:
        box_is_active(spc)
        spc.start_playback(device_id=DEVICE_ID, context_uri=spotify_uri)
    logging.info('Playing ' + spotify_uri)

def btn_volUp():
    global volumecurrent
    if volumecurrent < 100:
        volumecurrent += 10
        spc = connect()
        spc.volume(volumecurrent,device_id=DEVICE_ID)
        logging.info('Volume now at '+ volumecurrent)

def btn_volDown():
    global volumecurrent
    if volumecurrent > 0:
        volumecurrent -= 10
        spc = connect()
        spc.volume(volumecurrent,device_id=DEVICE_ID)
        logging.info('Volume now at ' + volumecurrent)

def btn_tracknext():
    spc = connect()
    try:
        spc.next_track()
        logging.info('Play next track')
    except Exception as e:
        logging.info('Playlist end')
        pass

def btn_trackprev():
    spc = connect()
    try:
        spc.previous_track()
        logging.info('Playing previous track')
    except Exception as e:
        logging.info('Beginning of playlist')
        pass

def btn_play():
    spc = connect()
    if spc.current_playback() and not spc.current_playback()['is_playing']:
        spc.start_playback()
        logging.info('Start playing')

def btn_pause():
    spc = connect()
    if spc.current_playback() and spc.current_playback()['is_playing']:
        spc.pause_playback()
        logging.info('Pause playing')

def btn_toggleplay():
    spc = connect()
    if spc.current_playback():
        if not spc.current_playback()['is_playing']:
            spc.start_playback()
            logging.info('Toggle -> Start playing')
        else:
            spc.pause_playback()
            logging.info('Toggle -> Pause playing')


