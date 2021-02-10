#!/usr/bin/env python3
"""
The game itself!

Much credit goes to the pygame maintainers for their wondeful, many-exampled library.
"""

#Change this stuff as you desire

SCREEN_WIDTH=550
SCREEN_HEIGHT=480
DELAY_FACTOR=3.0
# How many lines to /sync at a time. This can probably get pretty high,
# but shoddy netcode means that if it gets too high you might fill up a buffer or something.
SYNC_MULTIPLE=5

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
import vector as vec

# This has to happen first, even though most of main() we put at the end.
# This lets Pygame figure out what pixel format the screen uses, which
# has to be done before we load images (since we ask pygame to convert
# them to the screen's format)
if __name__ == "__main__":
    pg.init()
    screen = pg.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))

"""entities"""
class Entity:
    image = None
    obstructs = False
    visible = True
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
            self.dirty()
            get_tile(self.pos).rm(self)
        self.pos = pos
        if pos != None:
            get_tile(pos).add(self)
            self.dirty()

    def dirty(self):
        if self.pos != None:
            dirty_tiles.add(self.pos)

    def customhash(self):
        return (self.__class__.__name__, self.pos)

class MoveClaimToken(Entity):
    valid = True
    visible = False
    def __init__(self, pos):
        super().__init__(pos)
        """...eprint("Token created")"""
        " TODO delete __init__ "
    def move(self, pos):
        super().move(pos)
        if pos == None:
            return
        for ent in get_tile(pos).contents:
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
    spun_images = images.load_spun("icons", "move.png")

def set_teamed_skin(self, team):
    self.image = self.teamed_images[team]
def set_actor_skin(self, team):
    self.body_frames = self.teamed_body_frames[team]
    self.arm_frames = self.teamed_arm_frames[team]

class Corpse(Entity):
    obstructs = True
    teamed_images = images.load_teamed("units", "corpse.png")
    def __init__(self, pos, team):
        set_teamed_skin(self, team)
        super().__init__(pos)

team_bias_flips=[1,-1,1,-1,1,-1]
team_bias_angles=[a for a in range(6)]

# Cooldown keys. We use short strings b/c it looks legit
cd_move="mv"
cd_fight="atk"
cd_recover="rcvr"
# TODO What belongs to this class vs. Sword is a little vague,
#   should be move obvious where to draw the line when there are more units.
class Actor(Entity):
    obstructs = True
    def __init__(self, pos, team):
        self.team = team
        self.dead = False
        self.cooldowns = {cd_move: self.lap_time, cd_fight: self.fight_windup_time, cd_recover: 0}
        super().__init__(pos)
        self.ai = None
        self.tasks = []
        # Bias allows tie-breaking to be independent of absolute board orientation,
        # meaning so long as any start position can be rotated and/or flipped to look
        # like any other, the game can be made perfectly, completely fair.
        # ... Assuming I don't have any bugs.
        self.bias_flip = team_bias_flips[team]
        self.bias_angle = team_bias_angles[team]

    def draw(self, pos):
        frame = int(0 == self.cooldowns[cd_move])
        self._draw(pos, self.body_frames[frame])
        frame = (self.fight_windup_time - self.cooldowns[cd_fight]) * 2 // self.fight_windup_time
        self._draw(pos, self.arm_frames[frame])

    def move(self, pos):
        super().move(pos)
        self.cooldowns[cd_move] = self.lap_time
        self.cooldowns[cd_fight] = self.fight_windup_time

    def disintegrate(self):
        self.move(None)
        self.dead = True
        if self.ai != None:
            self.ai.clear_watches()
        # We don't cancel tasks, since some of them might be immediate by this point

    def die(self):
        corpse = Corpse(self.pos, self.team)
        tasks.schedule(tasks.Move(corpse, None), 90)
        self.disintegrate()

    def handle_finish(self, task):
        self.tasks.remove(task)
        if self.ai != None:
            # TODO as an optimization, there's probably no point in queueing the AI
            #   if we have an un-cancellable task in progress. Leaving it unoptimized
            #   for now, since it helps to make sure all the should_foo methods
            #   appropriately handle edge cases
            self.ai.queue_immediately()
    def handle_cancel(self, task):
        self.tasks.remove(task)
        if self.ai != None:
            self.ai.queue_immediately()

    def has_task(self, task):
        self.tasks.append(task)
        task.onfinish(self.handle_finish)
        task.oncancel(self.handle_cancel)

    def charge(self, cd_key):
        " Returns whether the given cooldown is ready to be used, and starts it charging if possible "
        # We can only charge one thing at a time
        for t in self.tasks:
            if type(t) == tasks.Charge and t.cd_key != cd_key:
                # Charging something else is just about the only thing we can interrupt at the moment
                continue
            return False
        # If we get to this point, any tasks left can be cancelled
        for t in self.tasks:
            t.cancel()
        # If it's already charged, we don't even have to make a task!
        # We still are correct to have cancelled the other tasks though;
        # typically using a cooldown means we want the others to stop charging.
        if self.cooldowns[cd_key] == 0:
            return True

        if cd_key == cd_fight:
            frame_times = [self.fight_windup_time // 2]
        else:
            frame_times = []

        self.has_task(tasks.Charge(self, cd_key, frame_times))
        return False

    def take_hit(self):
        self.has_task(tasks.Die(self))

    def should_navigate(self, pos):
        delta = vec.add(pos, vec.mult(self.pos, -1))
        angles = vec.calc_angles(delta, self.bias_flip)
        for angle in angles:
            if self.try_move(angle):
                return True
        return False
    def try_move(self, angle):
        # Charge first before checking destinations;
        # some obstructions are temporary, and we don't want to report a failure
        # until we're actually ready to move and the obstacle is still there.
        if not self.charge(cd_move):
            self.bias_angle = angle
            return True
        dest = vec.add(self.pos, vec.units[angle])
        if not is_walkable(get_tile(dest)):
            return False
        self.has_task(tasks.TokenResolver(self, MoveClaimToken(dest)))
        self.bias_angle = angle
        return True
    def should_fight(self, target):
        if not self.charge(cd_fight):
            return True
        self.cooldowns[cd_move] = self.lap_time
        self.cooldowns[cd_fight] = self.fight_windup_time
        self.dirty()
        self.has_task(tasks.Hit(target))
        return True
    def should_target(self, target):
        if self.is_loc_in_range(target.pos):
            return self.should_fight(target)
        else:
            return self.should_navigate(target.pos)
    def should_chill(self):
        self.charge(cd_fight) and self.charge(cd_move)
        return True
    def should_autofight(self):
        locs = self.get_locs_in_range()
        for loc in locs:
            target = self.choose_target(loc)
            if target != None:
                if not self.should_fight(target):
                    out("ERROR: should_fight returned False for a location in range with a valid target. %s %s->%s" % (self.__class__.__name__, str(self.pos), str(loc)))
                return True
        # If we were told to autofight, alert the AI if our options change
        for loc in locs:
            self.ai.watch(loc)
        return False

    def choose_target(self, loc):
        for x in get_tile(loc).contents:
            if isinstance(x, Actor) and x.team != self.team:
                return x
        return None
    def is_loc_in_range(self, loc):
        # TODO This can be made more efficient, need a vec.size function or something
        return loc in self.get_locs_in_range()
    def customhash(self):
        return (super().customhash(), self.team, self.ai)

class MeleeActor(Actor):
    def get_locs_in_range(self):
        ret = []
        for x in [0,1,-1,2,-2,3]:
            angle = (6 + x*self.bias_flip + self.bias_angle) % 6
            ret.append(vec.add(self.pos, vec.units[angle]))
        return ret

class Sword(MeleeActor):
    teamed_body_frames = images.load_teamed_anim("sword_body", 2)
    teamed_arm_frames = images.load_teamed_anim("sword_arm", 3)
    def __init__(self, pos, team):
        set_actor_skin(self, team)
        self.lap_time=360
        self.fight_windup_time=180
        super().__init__(pos, team)

class Archer(Actor):
    teamed_body_frames = images.load_teamed_anim("archer_body", 2)
    teamed_arm_frames = images.load_teamed_anim("archer_arm", 3)
    def __init__(self, pos, team):
        set_actor_skin(self, team)
        self.lap_time=360
        self.fight_windup_time=360 + 180
        super().__init__(pos, team)
    def get_locs_in_range(self):
        ret = []
        # Firstly, target anyone adjacent.
        # This is almost elegant, a list of angles offsets, as from MeleeActor.
        for x in [0,-1,1,-2,2,-3]:
            angle = (6 + x*self.bias_flip + self.bias_angle) % 6
            ret.append(vec.add(self.pos, vec.units[angle]))
        # Next, target people at range 2.
        # This should favor the space "ahead" of us (according to bias_angle)
        # and work back (in even pairs, resolving by bias_flip);
        # unfortuately, I can't tink of an elegant way to do this :(
        range_2_vecs = [
            ( 2, 0),
            ( 1, 1), ( 2,-1),
            ( 0, 2), ( 2,-2),
            (-1, 2), ( 1,-2),
            (-2, 2), ( 0,-2),
            (-2, 1), (-1,-1),
            (-2, 0)
        ]
        for v in range_2_vecs:
            ret.append(vec.add(self.pos, vec.transform(v, self.bias_flip, self.bias_angle)))
        return ret
"""end entities"""

"""symbols"""
symbols = []
class Symbol:
    def __init__(self, pos):
        self.pos = pos
        symbols.append(self)
    def draw(self):
        screen.blit(self.image, tile_to_screen(self.pos))
    def clear(self):
        dirty_tiles.add(self.pos)
    # Symbols are NOT hashed, they're part of local user HUD
class SelectSymbol(Symbol):
    image = images.load("icons", "select.png")
class TargetSymbol(Symbol):
    image = images.load("icons", "target.png")
def clear_symbols():
    global symbols
    for s in symbols:
        s.clear()
    symbols = []
"""end symbols"""

"""tiles"""
class TerrainGrass(Entity):
    image = images.load("tiles", "grass.png")

"""end tiles"""

"""board"""
class Tile:
    def __init__(self, contents):
        self.contents = contents
        self.watchers = []
    def add(self, ent):
        self.contents.append(ent)
        if ent.visible:
            # tile_update() typically cleans up watchers (while we're iterating it!),
            # so we have to make a quick dupe w/ slice notation
            for l in self.watchers[:]:
                l.tile_update()
    def rm(self, ent):
        self.contents.remove(ent)
        if ent.visible:
            for l in self.watchers:
                l.tile_update()
    def customhash(self):
        return (self.contents, len(self.watchers))
def complain(self):
    raise Exception("Invalid operation")
invalid_tile = Tile([])
invalid_tile.add = complain # Does this even work? Hope so!
invalid_tile.rm = complain

screen_offset_x = -TILE_WIDTH*5//2
screen_offset_y = 0

board = [[Tile([]) for i in range(11)] for j in range(11)]

def get_tile(pos):
    (x, y) = pos
    if x < 0 or x >= len(board):
        return invalid_tile
    row = board[x]
    if y < 0 or y >= len(row):
        return invalid_tile
    return row[y]
def is_walkable(tile):
    ents = tile.contents
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
    for entity in board[x][y].contents:
        entity.draw(pos)

screen_dirty = True
dirty_tiles = set()
def redraw():
    global screen_dirty
    global dirty_tiles
    if screen_dirty:
        screen_dirty = False
        screen.fill(0x000000)
        for x in range(0, len(board)):
            for y in range(0, len(board[x])):
                draw_tile((x, y))
    else:
        for pos in dirty_tiles:
            draw_tile(pos)
    dirty_tiles = set()
    for s in symbols:
        # TODO This should be improved if possible to track dirtiness, like tiles
        s.draw()
    pg.display.update()
"""end rendering"""

"""ai"""
class Ai(tasks.Task):
    def __init__(self, ent):
        super().__init__()
        self.ent = ent
        self.tiles = set()
        ent.ai = self
        self.is_queued = False
        self.queue_immediately()
    def watch(self, pos):
        self.tiles.add(pos)
        if not self.is_queued:
            raise Exception("AIs are only supposed to watch() while think()ing, and this clearly isn't!")
    def clear_watches(self):
        # TODO should clear on death, just for cleanliness
        for pos in self.tiles:
            get_tile(pos).watchers.remove(self)
        self.tiles = set()
    def run(self):
        if self.ent.dead:
            return False
        self.clear_watches()
        self.think()
        self.is_queued = False
        for pos in self.tiles:
            get_tile(pos).watchers.append(self)
    def queue_immediately(self):
        if self.is_queued:
            return
        self.clear_watches()
        self.is_queued = True
        tasks.immediately(tasks.THINK_PATIENCE, self)
    def tile_update(self):
        self.queue_immediately()
    def draw_symbols(self):
        pass
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
        self.queue_immediately()
    def todo_next(self, command):
        if self.todo:
            self.todo.append(command)
        else:
            self.todo_now(command)
    def mk_tile_command(self, pos):
        if get_tile(pos).contents:
            return GotoCommand(pos)
        return None
    def think(self):
        "Each time this loop restarts we assume the previous command 'completed'"
        "So we have to throw in a fake command for the first iteration"
        self.todo.insert(0, None)
        while True:
            self.todo.pop(0)
            if not self.todo:
                self.ent.should_autofight() or self.ent.should_chill()
                return
            command = self.todo[0]
            if command.mode == "goto":
                if command.pos == self.ent.pos:
                    continue
                if self.ent.should_autofight() or self.ent.should_navigate(command.pos):
                    return
                #Else, no path, abort command and fall thru
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
    for x in get_tile(pos).contents:
        if isinstance(x, Actor) and x.team in team:
            return x
def send_tile_command(ent, pos, append):
    ai = ent.ai
    " TODO Add team check "
    if isinstance(ai, ControlledAi):
        command = ai.mk_tile_command(pos)
        if command != None:
            m = ai.todo_next if append else ai.todo_now
            m(command)
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
        if src_filename[-3:] == ".gz":
            out("Interpreting .gz save as gzipped")
            shutil.copyfile(src_filename, log_filename)
        else:
            out("Interpreting non-.gz save as plain text (gzipping working copy)")
            tmp_in = open(src_filename, 'rb')
            tmp_out = gzip.open(log_filename, 'wb')
            tmp_out.write(tmp_in.read())
            tmp_in.close()
            tmp_out.close()
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
    # TODO Draw "loading" bar?
    next_time = tasks.next_time()
    while next_time < requested_time:
        requested_time -= next_time
        delay(next_time)
        tasks.wait_time(next_time)
        tasks.run()
        redraw()
        next_time = tasks.next_time()
    delay(requested_time)
    tasks.wait_time(requested_time)
    tasks.run(tasks.THINK_PATIENCE)
    redraw()

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
    redraw()

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
        unit=False
        if what == 'S':
            f = Sword
            unit=True
        elif what == 'A':
            f = Archer
            unit=True
        elif what == 'grass':
            f = TerrainGrass
        else:
            out("Don't know how to make a '%s'" % what)
            return False
        pos = (int(args[1]), int(args[2]))
        if len(args) == 4:
            created = f(pos, int(args[3]))
        else:
            created = f(pos)
        if unit:
            ControlledAi(created)
        redraw()
        return
    if command == "rm":
        pos = (int(args[0]), int(args[1]))
        content_copy = get_tile(pos).contents[:]
        for ent in content_copy:
            if isinstance(ent, Actor):
                ent.disintegrate()
            else:
                ent.move(None)
        # Have to redraw the whole screen, since there's nothing left on that tile
        # to cover up the previous pixels there
        global screen_dirty
        screen_dirty = True
        redraw()
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
    if command == "dehost":
        out("> %s has /dehost'ed" % who)
        if who == localname:
            host_mode = False
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
        return False

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
            send_tile_command(subject, dest, len(args) == 5)
            if subject.pos == selected:
                select(subject)
        return
    if command == "team":
        seat.team = [int(arg) for arg in args]
        out("> %s set their team to %s" % (who, str(seat.team)))
        return
    out("> %s issued unknown command %s" % (who, command))
    return False

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

    redraw()
    tasks.Keepalive()

    if len(sys.argv) > 4:
        host_hint = fast_forward_from_log(sys.argv[4])
        logfile = gzip.open(log_filename, "ab") # 'A'ppend 'B'inary mode
    else:
        host_hint = False
        logfile = gzip.open(log_filename, "wb")

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
            for i in range(SYNC_MULTIPLE):
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
                    break

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
                        modifier = " 1" if pg.KMOD_SHIFT & pg.key.get_mods() else ""
                        send("do %d %d %d %d%s\n" % (selected[0], selected[1], tile[0], tile[1], modifier))
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
