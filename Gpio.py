import spotycon

def gpio():
    
    print("start async gpio")
    from gpiozero import Button 
    from signal import pause 
    #from subprocess import check_call 

    #def do_shutdown(): 
        #check_call(['sudo', 'shutdown']) 
    def do_volUp():
        print("volup")
        spotycon.btn_volUp() 
    def do_volDown():
        print("vodown")
        spotycon.btn_volDown() 
    def do_next(): 
        print("next")
        spotycon.btn_tracknext()
    def do_prev(): 
        print("prev")
        spotycon.btn_trackprev()
    def do_playpause(): 
        print("toggle")
        spotycon.btn_toggleplay()

    #shutdown = Button(3, hold_time=2) 
    volUp = Button(16) #22
    volDown = Button(19) #23
    next = Button(26) #17
    prev = Button(20) #27
    playpause = Button(21, hold_time=0.3) #26

    #shutdown.when_held = do_shutdown 
    volUp.when_pressed = do_volUp
    volDown.when_pressed = do_volDown
    next.when_pressed = do_next
    prev.when_pressed = do_prev
    playpause.when_pressed = do_playpause

    pause()

gpio()