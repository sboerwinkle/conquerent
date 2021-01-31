#!/usr/bin/env python3
"""
The game itself!

Much credit goes to the pygame maintainers for their wondeful, many-exampled library.
"""

#Change this stuff as you desire
SCREEN_WIDTH=500
SCREEN_HEIGHT=500
DELAY_FACTOR=3.0

#Probably should not change this stuff
TILE_WIDTH=50
TILE_HEIGHT=43

import gzip
import io
import os
import pygame as pg
import shutil
from select import select as fd_select
import socket
import sys
import traceback

#Local imports
import tasks, images
from myhash import myhash

"""vectors"""
unit_vecs=[(1,0),(1,-1),(0,-1),(-1,0),(-1,1),(0,1)]
def vec_add(v1, v2):
    return (v1[0]+v2[0], v1[1]+v2[1])
def vec_mult(v1, c):
    return (v1[0]*c, v1[1]*c)
def calc_angle(v1, flip):
    (x,y) = v1
    def gr(a, b):
        if flip:
            return a >= b
        else:
            return a > b
    if x > 0:
        if y > 0:
            return 0 if gr(x, y) else 5
        y = -y
        if y > x:
            return 2 if gr(y, x*2) else 1
        else:
            return 1 if gr(y*2, x) else 0
    else:
        if y < 0:
            return 3 if gr(y, x) else 2
        x = -x
        if y > x:
            return 5 if gr(y, x*2) else 4
        else:
            return 4 if gr(y*2, x) else 3

"""end vectors"""

"""entities"""
class Entity:
    image = None
    obstructs = False
    def __init__(self, pos = None):
        self.pos = None
        self.move(pos)

    def draw(self, pos):
        if self.image == None:
            return
        self._draw(pos, self.image)
    def _draw(self, pos, image):
        screen.blit(image, tile_to_screen(pos))

    def move(self, pos):
        if self.pos != None:
            board[self.pos[0]][self.pos[1]].remove(self)
            """ TODO: Maybe should just dirty the tile? """
            draw_tile(self.pos)
        self.pos = pos
        if pos != None:
            board[pos[0]][pos[1]].append(self)
            self.draw(pos)

    def customhash(self):
        return (self.__class__.__name__, self.pos)

class MoveClaimToken(Entity):
    valid = True
    def __init__(self, pos):
        super().__init__(pos)
        """...eprint("Token created")"""
        " TODO delete __init__ "
    def move(self, pos):
        super().move(pos)
        if pos == None:
            return
        tile = get_tile(pos)
        for ent in tile:
            if ent.__class__ == MoveClaimToken and ent != self:
                self.valid = False
                ent.valid = False
                """...eprint("Token conflicted")"""
                return

class SpunEntity(Entity):
    def __init__(self, pos = None, angle = 0):
        self.angle = angle
        super().__init__(pos)
    def draw(self, pos):
        self._draw(pos, self.spun_images[self.angle])
    def customhash(self):
        return (angle, super().customhash())

class MovingIcon(SpunEntity):
    pass
images.queue_spun(MovingIcon, "icons", "move.png")

class Actor(Entity):
    obstructs = True
    def __init__(self, pos):
        super().__init__(pos)
        self.ai = None
        self.task = None
        " We want perfect symmetry, so in the future certain teams might be 'flipped' when it comes to left/right tie-breaking "
        self.flip = 1

    def move(self, pos):
        super().move(pos)
        self.move_charged = False

    def handle_finish(self):
        self.task = None
        if self.ai != None:
            self.ai.queue_immediately()

    def has_task(self, task):
        self.task = task
        task.then(self.handle_finish)
        task.oncancel(self.handle_finish)
    def charge_move(self):
        self.has_task(tasks.ChargeMove(self, self.lap_time))

    def should_move(self, angle):
        dest = vec_add(self.pos, unit_vecs[angle])
        if not is_walkable(get_tile(dest)):
            return False
        if isinstance(self.task, tasks.ChargeMove):
            return
        if self.task != None:
            self.task.cancel()
        if not self.move_charged:
            self.charge_move()
            return
        self.has_task(tasks.TokenResolver(self, MoveClaimToken(dest)))
    def should_chill(self):
        if self.task == None and not self.move_charged:
            self.charge_move()

    def customhash(self):
        if self.ai == None:
            return super().customhash()
        return (super().customhash(), self.ai.customhash())

class TeamedActor(Actor):
    def __init__(self, pos, team):
        self.image = self.teamed_images[team]
        self.team = team
        super().__init__(pos)
    def customhash(self):
        return (self.team, super().customhash())

class Guy(TeamedActor):
    def __init__(self, pos, team):
        super().__init__(pos, team)
        self.lap_time=360
images.queue_teamed(Guy, "units", "guy2.png")
"""end entities"""

"""symbols"""
symbols = []
class Symbol:
    def __init__(self, pos):
        self.pos = pos
        self.draw()
        symbols.append(self)
    def draw(self):
        screen.blit(self.image, tile_to_screen(self.pos))
    def clear(self):
        draw_tile(self.pos)
    # Symbols are NOT hashed, they're part of local user HUD
class SelectSymbol(Symbol):
    pass
images.queue(SelectSymbol, "icons", "select.png")
class TargetSymbol(Symbol):
    pass
images.queue(TargetSymbol, "icons", "target.png")
def clear_symbols():
    global symbols
    for s in symbols:
        s.clear()
    symbols = []
"""end symbols"""

"""tiles"""
"""Tiles don't do anything, so I don't need to ever instantiate more than one of each type"""
tile_grass = Entity()
images.queue(tile_grass, "tiles", "grass.png")

"""end tiles"""

"""board"""
BOARD=[[0,0,0,2,1,1,3],
        [0,0,1,2,0,3,1],
         [0,1,0,1,1,0,1],
          [7,7,1,1,1,4,4],
           [1,0,1,1,0,1,0],
            [1,6,0,5,1,0,0],
             [6,1,1,5,0,0,0]]
screen_offset_x = -TILE_WIDTH
screen_offset_y = 0

board = [[[tile_grass] if code!=0 else [] for code in row] for row in BOARD]

def get_tile(pos):
    (x, y) = pos
    if x < 0 or x >= len(board):
        return []
    row = board[x]
    if y < 0 or y >= len(row):
        return []
    return row[y]
def is_walkable(ents):
    if not ents:
        return False
    for e in ents:
        if e.obstructs:
            return False
    return True
"""end board"""

"""rendering"""
def tile_to_screen(pos):
    (x, y) = pos
    return ((screen_offset_x + TILE_WIDTH*x + int(TILE_WIDTH/2)*y), (screen_offset_y + TILE_HEIGHT*y))

def draw_tile(pos):
    (x,y)=pos
    for entity in board[x][y]:
        entity.draw(pos)

def draw_all_tiles():
    for x in range(0, len(board)):
        for y in range(0, len(board[x])):
            draw_tile((x, y))
"""end rendering"""

"""ai"""
class Ai(tasks.Task):
    def __init__(self, ent):
        super().__init__()
        self.ent = ent
        ent.ai = self
        self.is_queued = False
        self.queue_immediately()
    def _run(self):
        super()._run()
        self.is_queued = False
    def queue_immediately(self):
        if self.is_queued:
            return
        self.is_queued = True
        tasks.immediately(tasks.THINK_PATIENCE, self)
    def draw_symbols(self):
        pass
class WallAi(Ai):
    def __init__(self, ent):
        super().__init__(ent)
        self.angle = 0
    def run(self):
        for i in range(6):
            new_angle = (self.angle + i) % 6
            if self.ent.should_move(new_angle) != False:
                self.angle = new_angle
                return
        #eprint("Couldn't find anywhere to go, shutting down")
        self.ent.should_chill()
class Command:
    def __init__(self, mode):
        self.mode = mode
    def customhash(self):
        return self.mode
class GotoCommand(Command):
    def __init__(self, pos):
        super().__init__('goto')
        self.pos = pos
    def customhash(self):
        return (self.pos, super().customhash())
class ControlledAi(Ai):
    def __init__(self, ent):
        super().__init__(ent)
        self.todo = []
    def todo_now(self, command):
        self.todo = [command]
        tasks.Lambda(self.queue_immediately, 0)
    def todo_next(self, command):
        if self.todo:
            self.todo.append(command)
        else:
            self.todo_now(command)
    def mk_tile_command(self, pos):
        tile = get_tile(pos)
        if not tile:
            return None
        return GotoCommand(pos)
    def run(self):
        "Each time this loop restarts we assume the previous command 'completed'"
        "So we have to throw in a fake command for the first iteration"
        self.todo.insert(0, None)
        while True:
            self.todo.pop(0)
            if not self.todo:
                self.ent.should_chill()
                return
            command = self.todo[0]
            if command.mode == "goto":
                delta = vec_add(command.pos, vec_mult(self.ent.pos, -1))
                if delta == (0, 0):
                    continue
                flip = self.ent.flip
                angle = calc_angle(delta, flip)
                for delt in [0, flip, -flip]:
                    if self.ent.should_move((angle+delt+6)%6) != False:
                        return
                " Else, no path, abort command and fall thru "
            else:
                raise "Unknown command mode '%s'" % command.mode
    def draw_symbols(self):
        for command in self.todo:
            if command.mode == "goto":
                TargetSymbol(command.pos)
    def customhash(self):
        return (self.todo, super().customhash())
"""end ai"""

"""control"""
def mouse_to_tile(x, y):
    " For clicks, the grid is actually like staggered rectangular bricks, not actually hexes "
    x -= screen_offset_x
    y -= screen_offset_y
    " Yes, I know it's flipped "
    col = y // TILE_HEIGHT
    x -= int(TILE_WIDTH/2)*col
    row = x // TILE_WIDTH
    return (row, col)

def get_selectable(pos, team):
    contents = get_tile(pos)
    for x in get_tile(pos):
        if isinstance(x, TeamedActor) and x.team in team:
            return x
def send_tile_command(ent, pos):
    ai = ent.ai
    " TODO Add team check "
    if isinstance(ai, ControlledAi):
        command = ai.mk_tile_command(pos)
        if command != None:
            ai.todo_next(command)
"""end control"""

"""seats"""
class Seat:
    def __init__(self, name, team):
        self.name = name
        self.time = -1
        self.team = team
seats=[]
def get_team():
    for s in seats:
        if s.name == localname:
            return s.team
    return []
"""end seats"""

"""main stuff"""

fast_forward = False
host_mode = False
log_filename = "saves/log.%d.gz" % os.getpid()

uploading = False
downloading = False
net_input_paused = False
net_pause_queue = []
def pause_net_input():
    global net_input_paused
    net_input_paused = True
def resume_net_input():
    global net_input_paused
    global net_pause_queue
    net_input_paused = False
    # We aren't setting fast_forward, since this should be things that other people "recently" played thru.
    # We could, though, wouldn't be a huge deal
    for line in net_pause_queue:
        handle_net_bytes(line)
    net_pause_queue = []
    if net_input_paused:
        out("\n\n\nLooks like there were two /sync's going on at the same time.\nThis probably means multiple hosts, which is bad,\nbut in either case something's probably corrupt for someone now.\n\n\n")

def fast_forward_from_log(src_filename):
    try:
        shutil.copyfile(src_filename, log_filename)
    except:
        traceback.print_exc()
        eprint("Issue while trying to load from save '%s'" % src_filename)
        return False
    f = gzip.open(log_filename)
    out("Restoring state from %s..." % src_filename)
    global fast_forward
    fast_forward=True
    try:
        for line in f:
            handle_net_bytes(line, False)
    finally:
        fast_forward=False
        f.close()
    out("State restored.")
    return True

def delay(time):
    if not fast_forward:
        pg.time.wait(int(time * DELAY_FACTOR))

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)
def out(x):
    """The wrapper script for this game sends output to a pipe, which is very fond of buffering. Don't do that."""
    print(x)
    sys.stdout.flush()

def do_step(requested_time):
    next_time = tasks.next_time()
    while next_time <= requested_time:
        requested_time -= next_time
        delay(next_time)
        tasks.run(next_time)
        pg.display.update()
        next_time = tasks.next_time()
    delay(requested_time)
    "Won't run anything, but moves times up"
    tasks.run(requested_time)

selected = None
def select(target):
    global selected
    clear_symbols()
    if target == None:
        selected = None
    else:
        selected = target.pos
        SelectSymbol(selected)
        if target.ai != None:
            target.ai.draw_symbols()
    pg.display.update()

def handle_net_bytes(orig_bytes, do_log = True):
    if orig_bytes[0:1] == b'#':
        if not downloading:
            return
        orig_bytes = orig_bytes[1:]
    else:
        if net_input_paused:
            net_pause_queue.append(orig_bytes)
            return

    line = orig_bytes.decode('utf-8')
    "Parse out the command: '[who]:[command] [line]'"
    delim = line.index(":")
    who = line[0:delim]
    "Strip off newline here while we're also stripping the colon"
    line = line[delim+1:-1]
    if not (' ' in line):
        line = line + ' '
    delim = line.index(' ')
    command = line[0:delim]
    line = line[delim+1:]
    result = handle_net_command(who, command, line)
    if result != False and do_log:
        logfile.write(orig_bytes)

def handle_net_command(who, command, line):
    global downloading
    global fast_forward
    global host_mode
    " Returns False if the command had no impact on gamestate "
    args = line.split(' ')
    # Some commands don't require you to be seated
    if command == "say":
        out(who + ":  " + line)
        return False
    if command == "raw":
        out(line)
        return False
    if command == "seats":
        seats[:] = [Seat(args[i], [i]) for i in range(len(args))]
        out("> %s set the /seats to: %s" % (who, line))
        return
    if command == "callhash":
        out("> %s issued /callhash" % who)
        send("raw #%X for %s\n" % (myhash((board, tasks._pending)), localname))
        #send("raw #%X for %s\n" % (myhash(tasks._pending), localname))
        return False
    if command == "mk":
        what = args[0]
        if what == 'guy':
            f = Guy
        elif what == 'move':
            f = MovingIcon
        else:
            out("Don't know how to make a '%s'" % what)
            return
        pos = (int(args[1]), int(args[2]))
        if len(args) == 4:
            f(pos, int(args[3]))
        else:
            f(pos)
        pg.display.update()
        return
    if command == "join":
        out("> %s has joined" % who)
        if host_mode:
            send("sync %s\n" % who)
        return False
    if command == "host":
        out("> %s is now the /host" % who)
        host_mode = (who == localname)
        return False
    if command == "sync":
        out("> %s started /sync-ing to: %s" % (who, line))
        if who == localname:
            global uploading
            uploading = True
            pause_net_input()
            global logfile
            logfile.close()
            logfile = gzip.open(log_filename)
        elif localname in args:
            downloading = True
            fast_forward = True
            pause_net_input()
        return False
    if command == "syncdone":
        if downloading: # Which you always should be in this case
            out("---------- SYNC COMPLETE ----------")
        downloading = False
        fast_forward = False
        resume_net_input()
        return False

    for seat in seats:
        if seat.name == who:
            break
    else:
        out("Couldn't find seat for input %s:%s %s" % (who, command, line))
        return

    if command == "T":
        seat.time = int(line)
        ready_seats = []
        waiting_seats = []
        for s in seats:
            (waiting_seats if s.time < 0 else ready_seats).append(s.name)
        if len(waiting_seats) > 0:
            out("> %s confirmed, waiting on %s" % (str(ready_seats), str(waiting_seats)))
            return
        requested_time = min(s.time for s in seats)
        out("------------------------------")
        for s in seats:
            s.time = -1
        select(None)
        do_step(requested_time)
        return
    if command == "do":
        args = [int(a) for a in args]
        src = (args[0], args[1])
        dest = (args[2], args[3])
        subject = get_selectable(src, seat.team)
        if subject == None:
            out("Couldn't find a selectable thing at %s" % str(src))
        else:
            send_tile_command(subject, dest)
            if subject.pos == selected:
                select(subject)
        return
    if command == "team":
        seat.team = [int(arg) for arg in args]
        out("> %s set their team to %s" % (who, str(seat.team)))
        return
    out("> %s issued unknown command %s" % (who, command))
    return False

def spawn_units():
    for x in range(len(BOARD)):
        col = BOARD[x]
        for y in range(len(col)):
            cell = col[y]
            if cell <= 1:
                continue
            team = cell - 2
            ControlledAi(Guy((x,y), team))

def send(msg):
    server.send((localname + ":" + msg).encode('utf-8'))

def main():
    # Jesus take the wheel, I need some objects or something up in here
    global server
    global localname
    global uploading
    global logfile

    if (len(sys.argv) | 1) != 5: # hahahahahah
        eprint("Usage: %s name host port [save.gz]" % sys.argv[0])
        return
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.connect((sys.argv[2], int(sys.argv[3])))

    server_reader = server.makefile(mode='b', buffering=0) # Convenience so we don't have to mess with recv buffers
    # TODO: https://code.activestate.com/recipes/578900-non-blocking-readlines/
    # If that link dies, basically the gist of it is managing a buffer by hand;
    #   they use fcntl for non-blocking reads, but we could use our existing select() just fine.
    #   The reason this is necessary is b/c if I enable buffering on server_reader as-is,
    #   each time I fetch a line from it, it may fetch multiple from the underlying socket
    #   (which then reports as not ready for read),
    #   and I have no way of knowing how many lines I can read at that time.

    localname = sys.argv[1]
    global screen
    pg.init()
    screen = pg.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    images.load_queued()

    draw_all_tiles()
    pg.display.update()
    tasks.Keepalive()

    # Board setup stuff. Some things expect to happen in the framework of task evaluation,
    # e.g. tasks.immediately() calls work as expected,
    # so we throw the initial setup into the 0th "turn"
    tasks.Lambda(spawn_units, 0)
    do_step(0)

    if len(sys.argv) > 4:
        host_hint = fast_forward_from_log(sys.argv[4])
        logfile = gzip.open(log_filename, "ab") # 'A'ppend 'B'inary mode
    else:
        host_hint = False
        logfile = gzip.open(log_filename, "wb")

    #tasks.Lambda(lambda: ControlledAi(Guy((2,2))), 360)
    #tasks.Lambda(lambda: WallAi(Guy((2,2))), 360*5)
    # Setup input. This probably only works on Linux
    out("Initializing inputs")
    console_reader = io.open(sys.stdin.fileno())
    select(None)
    send('host\n' if host_hint else 'join\n')
    out("Starting main loop")

    running = True
    while running:
        # Rather than spin up two threads (ugh) we just poll both event sources at 20 Hz
        pg.time.wait(50)

        # If we're uploading, we write those lines out at 20Hz.
        # Yes, the whole "20Hz main loop" thing is dumb. You fix it then.
        if uploading:
            #pg.time.wait(200) # Testing only, should be commented
            line = logfile.readline()
            if line:
                server.send(b'#' + line)
            else:
                server.send(b'#:syncdone\n')
                send('callhash\n')
                uploading = False
                logfile.close()
                logfile = gzip.open(log_filename, 'ab')
                resume_net_input()

        # Read and process any lines waiting on the text inputs
        while True:
            to_read,_,_ = fd_select([server, sys.stdin], [], [], 0)
            if not to_read:
                break
            if server in to_read:
                # Note, here we're assuming there's a line available for reading, but we're only promised that there's *some* data
                orig_bytes = server_reader.readline()
                if not orig_bytes:
                    raise Exception("Server socket closed")

                try:
                    result = handle_net_bytes(orig_bytes)
                except Exception as err:
                    traceback.print_exc()
                    try:
                        print("Error while processing line: " + str(orig_bytes))
                    except:
                        print("Error while processing line which couldn't be displayed")
                    sys.stdout.flush()
            if sys.stdin in to_read:
                line = console_reader.readline()
                if not line:
                    running = False
                elif (line[0] == "/"):
                    send(line[1:])
                else:
                    send("say " + line)

        for event in pg.event.get():
            if event.type == pg.QUIT:
                running = False
            elif event.type == pg.MOUSEBUTTONDOWN:
                tile = mouse_to_tile(*pg.mouse.get_pos())
                if event.button == 1:
                    select(get_selectable(tile, get_team()))
                elif event.button == 3:
                    if selected != None:
                        send("do %d %d %d %d\n" % (selected[0], selected[1], tile[0], tile[1]))
                elif event.button == 2:
                    out("(" + str(tile) + ")")
            elif event.type == pg.KEYDOWN:
                if event.key == pg.K_SPACE:
                    send("T " + str(360*3) + "\n")
    send("raw > %s has left\n" % localname)
    logfile.close()
    server.close()
    os.rename(log_filename, "saves/most_recent.gz")

if __name__ == "__main__":
    main()
