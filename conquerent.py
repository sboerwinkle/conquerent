#!/usr/bin/env python3
"""
The game itself!

Much credit goes to the pygame maintainers for their wondeful, many-exampled library.
"""

SCREEN_WIDTH=500
SCREEN_HEIGHT=500

TILE_WIDTH=50
TILE_HEIGHT=43

DELAY_FACTOR = 3.0

import io
import os
import pygame as pg
from select import select as fd_select
import socket
import sys
import traceback

if not pg.image.get_extended():
    raise SystemExit("Extended image module req'd, aborting")

"""images"""
"""
You can't convert() / convert_alpha() until the display is set up,
but that doesn't happen until we're ready to start the game.
So, we just store references to objects here, and assign them an "image" attribute when it's time to do the image loading.
Because of how Python works, this also works to create class-level "image" attributes after the fact if desired.
"""
images_to_load=[]
teamed_colors=[(255, 0, 0, 255), (0xFF, 0x8f, 0x26, 255), (0x03, 0xC2, 0xFC, 255), (128, 128, 128, 255), (0x84, 0x03, 0xFC, 255), (0xFA, 0xAA, 0xF3, 255)]
class ImageSpec:
    pass
def queue_imgs(item, segments, mode):
    x = ImageSpec()
    x.item = item
    x.mode = mode
    x.path = os.path.join("assets", *segments)
    images_to_load.append(x)
def load_img(item, *segments):
    queue_imgs(item, segments, 'normal')
def load_spun_imgs(item, *segments):
    queue_imgs(item, segments, 'spun')
def load_teamed_imgs(item, *segments):
    queue_imgs(item, segments, 'teamed')
def load_queued_imgs():
    global images_to_load
    for spec in images_to_load:
        img = pg.image.load(spec.path).convert_alpha()
        item = spec.item
        if spec.mode == 'normal':
            item.image = img
        elif spec.mode == 'spun':
            item.spun_images = [img] + [rotate(img, deg) for deg in [60, 120, 180, -120, -60]]
        elif spec.mode == 'teamed':
            item.teamed_images = [dye(img, c) for c in teamed_colors]
    images_to_load = []
def rotate(img, degrees):
    "A wrapper around pygame's rotate that rotates about the center and keeps the dimensions the same"
    dest = pg.Surface(img.get_size(), pg.SRCALPHA, img)
    dest.fill(0)
    rotated = pg.transform.rotate(img, degrees)
    (dx, dy) = dest.get_rect().center
    (rx, ry) = rotated.get_rect().center
    dest.blit(rotated, (dx-rx, dy-ry))
    return dest
def dye(img, color):
    copy = img.copy()
    copy.fill(color, special_flags=pg.BLEND_RGBA_MULT)
    return copy
"""end images"""

"""vectors"""
unit_vecs=[[1,0],[1,-1],[0,-1],[-1,0],[-1,1],[0,1]]
def vec_add(v1, v2):
    return [v1[0]+v2[0], v1[1]+v2[1]]
def vec_mult(v1, c):
    return [v1[0]*c, v1[1]*c]
def calc_angle(v1, flip):
    [x,y] = v1
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

"""tasks"""
class Task:
    def __init__(self):
        self.listeners = []
        self.cancel_listeners = []
    def then(self, listener):
        self.listeners.append(listener)
    def oncancel(self, listener):
        self.cancel_listeners.append(listener)
    def _run(self):
        result = self.run()
        if isinstance(result, Task):
            "We can return a task to indicate a continuation, in that the original task's work isn't finished"
            "Combine the listener lists, and then point them to the same reference"
            self.listeners.extend(result.listeners)
            result.listeners = self.listeners
            self.cancel_listeners.extend(result.cancel_listeners)
            result.cancel_listeners = self.cancel_listeners
            return

        if result == None:
            to_run = self.listeners
        elif result == False:
            to_run = self.cancel_listeners
        else:
            raise Exception('Weird result from task', result)
        for l in to_run:
            l()
    def cancel(self):
        pending_tasks.remove(self)
        for l in self.cancel_listeners:
            l()
class KeepaliveTask(Task):
    """A dumb task that just makes sure the "minimum time to next task" is always well-defined, because it's always in the queue"""
    def __init__(self):
        super().__init__()
        self.time = 1000000
        pending_tasks.append(self)
    def run(self):
        KeepaliveTask()
class MoveTask(Task):
    def __init__(self, ent, pos):
        super().__init__()
        self.ent = ent
        self.pos = pos
    def run(self):
        """...eprint("Removing token")"""
        self.ent.move(self.pos)
class ChargeMoveTask(Task):
    def __init__(self, ent, time):
        super().__init__()
        self.time = time
        pending_tasks.append(self)
        self.ent = ent
    def run(self):
        """...eprint("Charged!")"""
        self.ent.move_charged = True
class TokenResolverTask(Task):
    def __init__(self, actor, token):
        super().__init__()
        immediately(0, self)
        self.actor = actor
        self.token = token
    def run(self):
        actor = self.actor
        token = self.token
        token.obstructs = True
        immediately(ACT_PATIENCE, MoveTask(token, None))
        if token.valid:
            """...eprint("Move accepted")"""
            task = MoveTask(actor, token.pos)
            immediately(ACT_PATIENCE, task)
            return task
        else:
            """...eprint("Couldn't move, conflicted")"""
            return False
class LambdaTask(Task):
    def __init__(self, l, time = None):
        super().__init__()
        if time != None:
            self.time = time
            pending_tasks.append(self)
        self.l = l
    def run(self):
        self.l()

pending_tasks=[]
immediate_tasks=[[]]
THINK_PATIENCE=1
ACT_PATIENCE=2
def immediately(patience, task):
    "add the task to the (patience)th immediate list."
    "If there aren't that many immediate lists yet, pad with empty lists."
    while len(immediate_tasks) <= patience:
        immediate_tasks.append([])
    immediate_tasks[patience].append(task)
def next_task_time():
    return min([t.time for t in pending_tasks])
def run_tasks(time):
    global pending_tasks
    """...eprint("----------")"""
    to_run = immediate_tasks[0]
    others = []
    for t in pending_tasks:
        if t.time == time:
            to_run.append(t)
        elif t.time > time:
            t.time -= time
            others.append(t)
        else:
            raise "Wrong time!"
    pending_tasks = others
    more_left = True
    while more_left:
        to_run = immediate_tasks[0]
        while to_run:
            t = to_run.pop(0)
            t._run()
        more_left = False
        for i in range(1, len(immediate_tasks)):
            if immediate_tasks[i]:
                """...eprint("-" * i)"""
                immediate_tasks[0] = immediate_tasks[i]
                immediate_tasks[i] = []
                more_left = True
                break
"""end tasks"""

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

class MovingIcon(SpunEntity):
    pass
load_spun_imgs(MovingIcon, "icons", "move.png")

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
        self.has_task(ChargeMoveTask(self, self.lap_time))

    def should_move(self, angle):
        dest = vec_add(self.pos, unit_vecs[angle])
        if not is_walkable(get_tile(dest)):
            return False
        if isinstance(self.task, ChargeMoveTask):
            return
        if self.task != None:
            self.task.cancel()
        if not self.move_charged:
            self.charge_move()
            return
        self.has_task(TokenResolverTask(self, MoveClaimToken(dest)))
    def should_chill(self):
        if self.task == None and not self.move_charged:
            self.charge_move()

class TeamedActor(Actor):
    def __init__(self, pos, team):
        self.image = self.teamed_images[team]
        self.team = team
        super().__init__(pos)

class Guy(TeamedActor):
    def __init__(self, pos, team):
        super().__init__(pos, team)
        self.lap_time=360
load_teamed_imgs(Guy, "units", "guy2.png")
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
class SelectSymbol(Symbol):
    pass
load_img(SelectSymbol, "icons", "select.png")
class TargetSymbol(Symbol):
    pass
load_img(TargetSymbol, "icons", "target.png")
def clear_symbols():
    global symbols
    for s in symbols:
        s.clear()
    symbols = []
"""end symbols"""

"""tiles"""
"""Tiles don't do anything, so I don't need to ever instantiate more than one of each type"""
tile_grass = Entity()
load_img(tile_grass, "tiles", "grass.png")

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
    [x, y] = pos
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
    [x, y] = pos
    return ((screen_offset_x + TILE_WIDTH*x + int(TILE_WIDTH/2)*y), (screen_offset_y + TILE_HEIGHT*y))

def draw_tile(pos):
    [x,y]=pos
    for entity in board[x][y]:
        entity.draw(pos)

def draw_all_tiles():
    for x in range(0, len(board)):
        for y in range(0, len(board[x])):
            draw_tile([x, y])
"""end rendering"""

"""ai"""
class Ai(Task):
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
        immediately(THINK_PATIENCE, self)
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
        eprint("Couldn't find anywhere to go, shutting down")
        self.ent.should_chill()
class Command:
    def __init__(self, mode):
        self.mode = mode
class ControlledAi(Ai):
    def __init__(self, ent):
        super().__init__(ent)
        self.todo = []
    def todo_now(self, command):
        self.todo = [command]
        LambdaTask(self.queue_immediately, 0)
    def todo_next(self, command):
        if self.todo:
            self.todo.append(command)
        else:
            self.todo_now(command)
    def mk_tile_command(self, pos):
        tile = get_tile(pos)
        if not tile:
            return None
        ret = Command('goto')
        ret.pos = pos
        return ret
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
                if delta == [0, 0]:
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
    return [row, col]

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
"""end seats"""

""" 'main' stuff """

def delay(time):
    pg.time.wait(int(time * DELAY_FACTOR))

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)
def out(x):
    """The wrapper script for this game sends output to a pipe, which is very fond of buffering. Don't do that."""
    print(x)
    sys.stdout.flush()

def do_step(requested_time):
    next_time = next_task_time()
    while next_time <= requested_time:
        requested_time -= next_time
        delay(next_time)
        run_tasks(next_time)
        pg.display.update()
        next_time = next_task_time()
    delay(requested_time)
    "Won't run anything, but moves times up"
    run_tasks(requested_time)

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

def handle_net_command(seats, who, command, line):
    args = line.split(' ')
    # Some commands don't require you to be seated
    if command == "say":
        out(who + ":  " + line)
        return
    if command == "raw":
        out(line)
        return
    if command == "seats":
        seats[:] = [Seat(args[i], [i]) for i in range(len(args))]
        out("> %s set the seats to %s" % (who, str([s.name for s in seats])))
        return
    if command == "mk":
        what = args[0]
        if what == 'guy':
            f = Guy
        elif what == 'move':
            f = MovingIcon
        else:
            eprint("Don't know how to make a '%s'" % what)
            return
        pos = [int(args[1]), int(args[2])]
        if len(args) == 4:
            f(pos, int(args[3]))
        else:
            f(pos)
        pg.display.update()
        return

    for seat in seats:
        if seat.name == who:
            break
    else:
        eprint("Couldn't find seat for input %s:%s %s" % (who, command, line))
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
        src = args[0:2]
        dest = args[2:4]
        subject = get_selectable(src, seat.team)
        if subject == None:
            eprint("Couldn't find a selectable thing at %s" % str(src))
        else:
            send_tile_command(subject, dest)
            if subject.pos == selected:
                select(subject)
        return
    if command == "team":
        seat.team = [int(arg) for arg in args]
        out("> %s set their team to %s" % (who, str(seat.team)))
        return

def spawn_units():
    for x in range(len(BOARD)):
        col = BOARD[x]
        for y in range(len(col)):
            cell = col[y]
            if cell <= 1:
                continue
            team = cell - 2
            ControlledAi(Guy([x,y], team))

def main():
    if len(sys.argv) != 4:
        eprint("Usage: %s name host port" % sys.argv[0])
        return
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.connect((sys.argv[2], int(sys.argv[3])))
    server_reader = server.makefile() # Convenience so we don't have to mess with recv buffers
    localname = sys.argv[1]
    seats = []
    def send(msg):
        server.send((localname + ":" + msg).encode('utf-8'))
    def get_team():
        for s in seats:
            if s.name == localname:
                return s.team
        return []
    global screen
    pg.init()
    screen = pg.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    load_queued_imgs()
    draw_all_tiles()
    pg.display.update()
    KeepaliveTask()

    # Board setup stuff. Some things expect to happen in the framework of task evaluation,
    # e.g. immediately() calls work as expected,
    # so we throw the initial setup into the 0th "turn"
    LambdaTask(spawn_units, 0)
    do_step(0)

    #LambdaTask(lambda: ControlledAi(Guy([2,2])), 360)
    #LambdaTask(lambda: WallAi(Guy([2,2])), 360*5)
    # Setup input. This probably only works on Linux
    out("Initializing inputs")
    console_reader = io.open(sys.stdin.fileno())
    running = True
    select(None)
    out("Starting main loop")
    while running:
        " Rather than spin up two threads (ugh) we just poll both event sources at 20 Hz "
        pg.time.wait(50)
        " Read and process any lines waiting on the text inputs "
        while True:
            to_read,_,_ = fd_select([server, sys.stdin], [], [], 0)
            if not to_read:
                break
            if server in to_read:
                # Note, here we're assuming there's a line available for reading, but we're only promised that there's *some* data
                orig = server_reader.readline()
                if not orig:
                    raise Exception("Server socket closed")

                try:
                    "Parse out the command: '[who]:[command] [line]'"
                    delim = orig.index(":")
                    who = orig[0:delim]
                    "Strip off newline here while we're also stripping the colon"
                    line = orig[delim+1:-1]
                    if not (' ' in line):
                        line = line + ' '
                    delim = line.index(' ')
                    command = line[0:delim]
                    line = line[delim+1:]
                    handle_net_command(seats, who, command, line)
                except Exception as err:
                    print("Error while processing line: " + orig)
                    traceback.print_exc()
                    sys.stdout.flush()
            if sys.stdin in to_read:
                line = console_reader.readline()
                if (line[0] == "/"):
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

if __name__ == "__main__":
    main()
