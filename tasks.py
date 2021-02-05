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
class Keepalive(Task):
    """A dumb task that just makes sure the "minimum time to next task" is always well-defined, because it's always in the queue"""
    def __init__(self):
        super().__init__(1000000)
    def run(self):
        Keepalive()
class Move(Task):
    def __init__(self, ent, pos):
        super().__init__()
        self.ent = ent
        self.pos = pos
    def run(self):
        """...eprint("Removing token")"""
        self.ent.move(self.pos)
class Charge(Task):
    def __init__(self, ent, cd_key):
        self.cd_key = cd_key
        self.ent = ent
        super().__init__(ent.cooldowns[cd_key])
    def run(self):
        self.ent.cooldowns[self.cd_key] = 0
    def cancel(self):
        self.ent.cooldowns[self.cd_key] = self.time
        super().cancel()
class TokenResolver(Task):
    def __init__(self, actor, token):
        super().__init__()
        immediately(0, self)
        self.actor = actor
        self.token = token
    def run(self):
        actor = self.actor
        token = self.token
        token.obstructs = True
        immediately(ACT_PATIENCE, Move(token, None))
        if token.valid:
            """...eprint("Move accepted")"""
            task = Move(actor, token.pos)
            immediately(ACT_PATIENCE, task)
            actor.has_task(task)
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
    def __init__(self, actor):
        super().__init__()
        # Only reason this isn't just a method is because there are other concurrent actions that might want to go through
        immediately(0, self)
        self.actor = actor
    def run(self):
        self.actor.move(None)
        self.actor.dead = True

class Lambda(Task):
    def __init__(self, l, time = None):
        super().__init__(time)
        self.l = l
    def run(self):
        self.l()

_pending=[]
_immediates=[[]]
running = False
THINK_PATIENCE=1
ACT_PATIENCE=2
def immediately(patience, task):
    "add the task to the (patience)th immediate list."
    "If there aren't that many immediate lists yet, pad with empty lists."
    if running:
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
def run():
    global running
    running = True
    global _pending
    """...eprint("----------")"""
    others = []
    for t in _pending:
        if t.time == 0:
            immediately(t.patience, t)
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
    running = False
