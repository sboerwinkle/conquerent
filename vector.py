units=[(1,0),(1,-1),(0,-1),(-1,0),(-1,1),(0,1)]
def add(v1, v2):
    return (v1[0]+v2[0], v1[1]+v2[1])
def sub(v1, v2):
    return (v1[0]-v2[0], v1[1]-v2[1])
def mult(v1, c):
    return (v1[0]*c, v1[1]*c)

def measure(v):
    (x,y) = v
    if x*y >= 0:
        return abs(x+y)
    return max(abs(x), abs(y))

# This function lovingly constructed on graph paper!
# Returns a list of angles to try to reach that vector, in preference order.
# Only returns angles that will reduce the "true" (euclidean) distance to the target.
def calc_angles(v1, flip):
    if v1 == (0,0):
        return []
    (x,y)=v1
    def gr(a,b):
        if flip == 1:
            return a >= b
        else:
            return a > b
    # e() handles when x >= y >= 0
    def e(x,y):
        if x == y:
            return [0,5]
        if x == 1 and y == 0:
            return [0]
        return [0,5,1]
    # f() handles when x>=0 and y>=0
    # This one is allowed to introduce a flip since e() doesn't care abt the value of flip
    def f(x,y):
        if gr(y,x):
            return [5-a for a in e(y,x)]
        return e(x,y)
    # g() handles when y >= 0
    def g(x,y):
        if gr(0,x):
            if gr(-x,y):
                return [(a+4)%6 for a in f(y,-x-y)]
            else:
                return [(a+5)%6 for a in f(y+x,-x)]
        else:
            return f(x,y)
    if y > 0 or (y == 0 and x*flip > 0):
        return g(x,y)
    return [(a+3)%6 for a in g(-x,-y)]

def transform(v, flip, rot):
    """Scales the vector perpendicular to the X axis by 'flip' (typically 1 or -1) and then rotates by 'rot'.
    flip must be an odd number."""
    (x,y) = v

    x = x + y*(1-flip)//2
    y = y * flip

    x_contrib = mult(units[rot], x)
    y_contrib = mult(units[(rot+5)%6], y)

    return add(x_contrib, y_contrib)
