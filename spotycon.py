import spotipy
from spotipy.oauth2 import SpotifyOAuth

#match this with libresport default volume inside CONF
volumecurrent = 60
playing = False

# 1) a app must be created, write down keys to below
# https://developer.spotify.com/dashboard/applications
# alternate set env vars
# export SPOTIPY_CLIENT_ID='xxx'
# export SPOTIPY_CLIENT_SECRET='xxx'
# export SPOTIPY_REDIRECT_URI='http://localhost:8080'
# ^be shure to use url with a port like this!

CLIENT_ID: str = 'xxx'
CLIENT_SECRET: str = 'xxx'
REDIRECT_URI: str = 'http://localhost:8080'

# 2) !give your app access once using a -non headless- machine, it will open a webbrowser!
# ->run connect_firstauth() from RfSpoty
# if you need auth for another user, there is a .cache in the .py folder -> just delete it 
# -> copy over to your headless machine

# 3) I think you need to get device ID for the raspoty-box, once with debug, and use it...

DEVICE_ID = 'xxx'

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

def playcard(cardID):
    spc = connect()

    # get dict (getting it late -> you can make changes anytime)
    d = {}
    with open("cards.txt") as f:
        for line in f:
            ll = line.split(" #")[0] # comments so you can write down the Album/Playlist name
            (key, val) = ll.split()
            d[key] = val

    print(d[cardID])

    #playback
    #spc.transfer_playback(device_id=DEVICE_ID, force_play=True)
    spc.start_playback(device_id=DEVICE_ID, context_uri=d[cardID])
    #spc.volume(volumestart,device_id=DEVICE_ID)
    playing = True

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

def btn_toggleplay():
    spc = connect()
    global playing
    if playing:
        spc.pause_playback(device_id=DEVICE_ID)
        playing = False
    else:
        spc.start_playback(device_id=DEVICE_ID)
        playing = True
