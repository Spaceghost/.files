#!/usr/bin/env python3
"""Synthetic terminal content for the private native concept preview."""
import sys
import time
import io

gold = '\033[38;2;250;189;47m'
cream = '\033[38;2;235;219;178m'
muted = '\033[38;2;168;153;132m'
green = '\033[38;2;184;187;38m'
blue = '\033[38;2;131;165;152m'
reset = '\033[0m'
bold = '\033[1m'
time.sleep(1)
terminal = sys.stdout
sys.stdout = io.StringIO()
print('\033[?25l', end='')

if sys.argv[1] == 'field':
    print(f'{gold}G H O S T   O B S E R V A T O R Y{reset}\n')
    print(f'{cream}{bold}A small room. A very large universe.{reset}\n')
    print(f'{muted}FIELD NOTES    001 / YOSEMITE{reset}')
    print(f'{cream}Golden hour, with an unlicensed tour guide.{reset}\n')
    print(f'{blue}“Nature has excellent ratings.”  — Space Ghost{reset}')
elif sys.argv[1] == 'desk':
    print(f'{muted}MBP_INTEL  /  RESEARCH DESK                         {green}● READY{reset}\n')
    print(f'{gold}{bold}Make room for a better view.{reset}\n')
    print(f'{cream}The mountains stay. The work keeps moving.{reset}\n')
    print(f'{muted}COLLECTION{reset}')
    print(f'{gold}  01{reset}  American Ghostic       {muted}oil / after hours{reset}')
    print(f'{blue}  02{reset}  Nighthawks             {muted}coffee / transmission{reset}')
    print(f'{green}  03{reset}  Yosemite               {muted}the current exhibition{reset}\n')
    print(f'{muted}ACTIONS{reset}')
    print(f'{cream}  click → next      scroll → browse      right → gallery{reset}')
    print(f'{cream}  super + click → create a new view{reset}\n')
    print(f'{gold}~/observatory {green}❯{reset} {cream}fossil status{reset}')
    print(f'{muted}  A place for the work. A record of how it was made.{reset}')
else:
    print(f'{green}● {muted}TRANSMISSION / COAST TO COAST{reset}\n')
    print(f'{cream}Zorak: Is this a computer or a national park?{reset}')
    print(f'{gold}Ghost: Both. Please stop eating the exhibits.{reset}\n')
    print(f'{muted}WORKSPACES     {gold}01 desk{muted}  /  02 studio  /  03 signals{reset}')
content = sys.stdout.getvalue()
sys.stdout = terminal
for _ in range(120):
    print('\033[H\033[2J' + content, end='', flush=True)
    time.sleep(1)
