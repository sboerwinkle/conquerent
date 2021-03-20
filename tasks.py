"""Definitions for various types of tasks, and the machinery needed to run them"""

class Task:
    def __init__(self, time=None, patience=0):
        self.listeners = []
        self.cancel_listeners = []
        self.time = time
        self.patience = patience
        if time != None:
            _pending.append(self)
    def onfinish(self, listener):
        self.listeners.append(listener)
    def oncancel(self, listener):
        self.cancel_listeners.append(listener)
    def _run(self):
        result = self.run()
        #if isinstance(result, Task):
        #    "We can return a task to indicate a continuation, in that the original task's work isn't finished"
        #    "Combine the listener lists, and then point them to the same reference"
        #    self.listeners.extend(result.listeners)
        #    result.listeners = self.listeners
        #    self.cancel_listeners.extend(result.cancel_listeners)
        #    result.cancel_listeners = self.cancel_listeners
        #    return

        if result == None:
            to_run = self.listeners
        elif result == False:
            to_run = self.cancel_listeners
        else:
            raise Exception('Weird result from task', result)
        for l in to_run:
            l(self)
    def cancel(self):
        _pending.remove(self)
        for l in self.cancel_listeners:
            l(self)
    def customhash(self):
        return (self.__class__.__name__, self.time)
class BlankTask(Task):
    "Basically a timer. Takes no action on its own."
    def run(self):
        pass
class Keepalive(Task):
    """A dumb task that just makes sure the "minimum time to next task" is always well-defined, because it's always in the queue"""
    def __init__(self):
        super().__init__(1000000)
    def run(self):
        Keepalive()
class Move(Task):
    def __init__(self, ent, pos):
        super().__init__(patience=ACT_PATIENCE)
        self.ent = ent
        self.pos = pos
    def run(self):
        """...eprint("Removing token")"""
        self.ent.move(self.pos)

class DumbChargeTask(Task):
    def __init__(self, ent, cd_key, amt, delay):
        self.ent = ent
        self.cd_key = cd_key
        self.amt = amt
        super().__init__(delay)
    def run(self):
        self.ent.cooldowns[self.cd_key] = self.amt
        self.ent.dirty()
    def cancel(self):
        if self.time == 0:
            raise Exception("Not supposed to cancel a DumbChargeTask with zero time!")
            # This shouldn't even be possible, but it means we'll probably miss marking the ent as dirty.
        super().cancel()
class Charge(DumbChargeTask):
    def __init__(self, ent, cd_key, frame_times):
        cd = ent.cooldowns[cd_key]
        # Contract here is that nobody cancels my kids except me, so they'll always finish in reverse order,
        # unless I cancel them first!
        self.kids = [DumbChargeTask(ent, cd_key, t, cd - t) for t in frame_times if t < cd]
        for k in self.kids:
            k.onfinish(self.pop_kid)
        super().__init__(ent, cd_key, 0, cd)
    def pop_kid(self, kid):
        self.kids.remove(kid)
    def cancel(self):
        self.ent.cooldowns[self.cd_key] = self.time
        for k in self.kids:
            k.cancel()
        super().cancel()
class TokenResolver(Task):
    def __init__(self, f, token):
        super().__init__()
        immediately(0, self)
        self.f = f
        self.token = token
    def run(self):
        token = self.token
        token.obstructs = True
        immediately(ACT_PATIENCE, Move(token, None))
        if token.valid:
            self.f(token.pos)
            """...eprint("Move accepted")"""
            return
        else:
            """...eprint("Couldn't move, conflicted")"""
            return False
class Hit(Task):
    def __init__(self, target):
        super().__init__()
        # Hitting is an action, and resolves with the other actions
        immediately(ACT_PATIENCE, self)
        self.target = target
    def run(self):
        self.target.take_hit()
class Die(Task):
    def __init__(self, actor, time=0, patience=0):
        super().__init__()
        # Even if time is 0, there are other concurrent actions that might want to go through, like moving
        schedule(self, time, patience)
        self.actor = actor
    def run(self):
        self.actor.die()
class Capture(Task):
    def __init__(self, actor, castle):
        super().__init__()
        immediately(ACT_PATIENCE, self)
        self.actor = actor
        self.castle = castle
    def run(self):
        # TODO __class__ stuff is a gross hack, needs to be better eventually
        self.castle.convert(self.actor.team, self.actor.__class__)
        self.actor.disintegrate()

class Lambda(Task):
    def __init__(self, l, time, patience):
        super().__init__()
        self.l = l
        # TODO This maybe should be default Task behavior?
        schedule(self, time, patience)
    def run(self):
        self.l()

_pending=[]
_immediates=[[]]
running = 0
THINK_PATIENCE=1
ACT_PATIENCE=2
SLOW_PATIENCE=3
MAX_PATIENCE=4
def schedule(task, time, patience=None):
    "Some tasks will auto-schedule themselves on construction, but this is useful for the others."
    if patience != None:
        task.patience = patience
    if time == 0:
        immediately(task.patience, task) # This makes sense right?
    else:
        task.time = time
        _pending.append(task)
def immediately(patience, task):
    "add the task to the (patience)th immediate list."
    "If there aren't that many immediate lists yet, pad with empty lists."
    if patience < running:
        while len(_immediates) <= patience:
            _immediates.append([])
        _immediates[patience].append(task)
    else:
        task.time = 0
        task.patience = patience
        _pending.append(task)
def next_time():
    return min([t.time for t in _pending])
def wait_time(time):
    if time > next_time():
        raise Exception("Having a bad time")
    for t in _pending:
        t.time -= time
def run(patience = MAX_PATIENCE):
    global running
    running = patience
    global _pending
    """...eprint("----------")"""
    others = []
    for t in _pending:
        if t.time == 0 and t.patience < running:
            immediately(t.patience, t)
        elif t.time < 0:
            raise Exception("Negative time on a task!")
        else:
            others.append(t)
    _pending = others
    while True:
        for i in range(0, len(_immediates)):
            if _immediates[i]:
                """...eprint("-" * i)"""
                tmp = _immediates[i]
                _immediates[i] = []
                _immediates[0] = tmp
                break
        else:
            break # The dreaded python for/else construct
        to_run = _immediates[0]
        while to_run:
            t = to_run.pop(0)
            t._run()
    running = 0
