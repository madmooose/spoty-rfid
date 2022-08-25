#!/usr/bin/env python3

import os
import spotycon

spc=spoticon.connect()
if not spotycon.is_active(spc):
    os.system("systemctl restart raspotify")