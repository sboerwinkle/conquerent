"""Definitions for various types of tasks, and the machinery needed to run them"""

class Task:
    def __init__(self, time=None):
        self.listeners = []
        self.cancel_listeners = []
        self.time = time
        if time != None:
            _pending.append(self)
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
        _pending.remove(self)
        for l in self.cancel_listeners:
            l()
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
class ChargeMove(Task):
    def __init__(self, ent, time):
        super().__init__(time)
        self.ent = ent
    def run(self):
        """...eprint("Charged!")"""
        self.ent.move_charged = True
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
            return task
        else:
            """...eprint("Couldn't move, conflicted")"""
            return False
class Lambda(Task):
    def __init__(self, l, time = None):
        super().__init__(time)
        self.l = l
    def run(self):
        self.l()

_pending=[]
_immediates=[[]]
THINK_PATIENCE=1
ACT_PATIENCE=2
def immediately(patience, task):
    "add the task to the (patience)th immediate list."
    "If there aren't that many immediate lists yet, pad with empty lists."
    while len(_immediates) <= patience:
        _immediates.append([])
    _immediates[patience].append(task)
def next_time():
    return min([t.time for t in _pending])
def run(time):
    global _pending
    """...eprint("----------")"""
    to_run = _immediates[0]
    others = []
    for t in _pending:
        if t.time == time:
            to_run.append(t)
        elif t.time > time:
            t.time -= time
            others.append(t)
        else:
            raise "Wrong time!"
    _pending = others
    more_left = True
    while more_left:
        to_run = _immediates[0]
        while to_run:
            t = to_run.pop(0)
            t._run()
        more_left = False
        for i in range(1, len(_immediates)):
            if _immediates[i]:
                """...eprint("-" * i)"""
                _immediates[0] = _immediates[i]
                _immediates[i] = []
                more_left = True
                break
