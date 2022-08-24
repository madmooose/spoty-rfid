#!/usr/bin/env python3

import os
import spotycon

if not spotycon.is_active():
    os.system("systemctl restart raspotify")