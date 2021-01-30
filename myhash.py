"""
Python expects hashes to be constant, i.e. you're not supposed to hash mutable objects.
However, we definitely want to hash some mutable things to get a game state;
to avoid causing headaches in the future, however, we put this in a custom hash function
so we don't trample the existing semantics.
"""
import sys

prime=23
# 24 bits is unrelated to the choice of prime, I just like the way 6 hex digits looks.
num_bytes=3
bits=num_bytes*8
mask=(1<<bits)-1

def myhash(arg):
    """
    Hashes the (possibly mutable) argument.
    Accepts None, int, str, objects defining customhash(), and tuples or lists thereof.
    Notably, does not currently accept bools or floats.
    """
    ret = 1
    def append(num):
        nonlocal ret
        # 23 is a nice prime
        ret = ret*prime + num
        ret = (ret ^ ret>>bits) & mask

    while True:
        if arg == None:
            return ret
        t = type(arg)
        if t == str:
            for i in range(0, len(arg), num_bytes):
                append(int.from_bytes(arg[i:i+num_bytes].encode('utf-8'), 'big'))
            return ret
        if t == int:
            while abs(arg) > 0xFFFFFF:
                arg = (arg >> bits) ^ (arg & mask)
            return arg & mask
        if t == list or t == tuple:
            for i in range(len(arg)):
                append(myhash(arg[i]))
            return ret
        # Otherwise it has to define customhash() to get a hashable representation, so try again
        arg = arg.customhash()
