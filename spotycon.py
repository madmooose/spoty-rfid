import spotipy
import subprocess
from spotipy.oauth2 import SpotifyOAuth
import config

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

def connect_firstauth():
    # connect to spotify app and auth with browser
    scope = "user-read-playback-state,user-modify-playback-state"
    sp = spotipy.Spotify(client_credentials_manager=SpotifyOAuth(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI, scope=scope,open_browser=True))

    #3) aiming device ^^ DEVICE_ID
    res = sp.devices()

    sp.start_playback(device_id=DEVICE_ID, context_uri='spotify:playlist:INSERTANYPLAYLISTHERE')
    print("")
    sp.pause_playback()
    return sp

def connect():
    scope = "user-read-playback-state,user-modify-playback-state"
    sp = spotipy.Spotify(client_credentials_manager=SpotifyOAuth(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI, scope=scope,open_browser=False))
    if not is_active(sp):
        print("Restarting librespot")
        subprocess.call("sudo systemctl restart raspotify")
    return sp

def is_active(spc):
    devices = spc.devices()['devices']
    for device in devices:
        if (device['id'] == DEVICE_ID):
            return True
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
            btn_toggleplay()
        elif d[cardID] == "pause":
            btn_toggleplay()
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
        else:
            do_play(d[cardID])
    else:
        print("Add {!r} to your cards.txt".format(cardID))

def do_play(spotify_uri):
    spc = connect()
    spc.start_playback(device_id=DEVICE_ID, context_uri=spotify_uri)

def btn_volUp():
    global volumecurrent
    if volumecurrent < 100:
        volumecurrent += 10
        spc = connect()
        spc.volume(volumecurrent,device_id=DEVICE_ID)

def btn_volDown():
    global volumecurrent
    if volumecurrent > 0:
        volumecurrent -= 10
        spc = connect()
        spc.volume(volumecurrent,device_id=DEVICE_ID)

def btn_tracknext():
    spc = connect()
    try:
        spc.next_track(device_id=DEVICE_ID)
    except Exception as e:
        pass

def btn_trackprev():
    spc = connect()
    try:
        spc.previous_track(device_id=DEVICE_ID)
    except Exception as e:
        pass

def btn_play():
    spc = connect()
    if spc.current_playback() and not spc.current_playback()['is_playing']:
        spc.start_playback(device_id=DEVICE_ID)

def btn_pause():
    spc = connect()
    if spc.current_playback() and spc.current_playback()['is_playing']:
        spc.pause_playback(device_id=DEVICE_ID)

def btn_toggleplay():
    spc = connect()
    if spc.current_playback():
        if not spc.current_playback()['is_playing']:
            btn_play()
        else:
            btn_pause()


