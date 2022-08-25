import spotipy
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

# 3) Get device it from Developer Console and put it in config.py



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
    return sp

def is_active():
    spc = connect()
    devices = spc.devices()['devices']
    for device in devices:
        if (device['id'] == DEVICE_ID and device['is_active'] == True):
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
    spc.next_track(device_id=DEVICE_ID)

def btn_trackprev():
    spc = connect()
    spc.previous_track(device_id=DEVICE_ID)

def btn_play():
    spc = connect()
    if not spc.current_playback()['is_playing']:
        spc.start_playback(device_id=DEVICE_ID)

def btn_pause():
    spc = connect()
    if spc.current_playback()['is_playing']:
        spc.pause_playback(device_id=DEVICE_ID)

def btn_toggleplay():
    spc = connect()
    if spc.current_playback()['is_playing']:
        btn_pause()
    else:
        btn_play()


