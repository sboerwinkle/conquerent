CONQUERENT
==========

A shitty strategy game for 0-6 players. Right now it's not even so much a game tbh

## Requirements

At the moment this only runs on Linux, but that might change in the future since it's primarily Python

- Bash
- python3
- pygame

## First Time Setup

If you're just joining someone else's game, you'll want to read the sections "Client" and "Controls", and probably "Mechanics".

If you're hosting or just messing around on your own, you should probably read the whole guide.

## Server

`./chat_server.py`

The server is extremely dumb. It accepts TCP connections on a port (specified as an optional argument, and the only argument), and then echoes any messages it gets to everyone on the server. This includes the person who sent the message, which is actually kinda nice so everyone gets a consistent order. You could use it for other things theoretically.

Anyway, launch that first. Since the server doesn't manage any game logic, there's no such thing as a "private" game beyond what your firewall or general anonymity can provide.

## Client

`./game.sh joe localhost 15000`

The client is best invoked from game.sh, which accepts 3 arguments: name, host, and port. "name" must be unique among clients, and should probably just be letters, but I think technically anything satisfying the regex `[^#: ][^: ]*` *should* work.

### Output

The first time you run game.sh you'll get a screed about the `output-script`. Read it, I'm not repeating myself here - I promise it's not difficult setup.

### Input

Chat is entered via the console (the terminal window where you launched the game). This is also where commands are issued - check out the "Commands" section for more info.

## Controls

Click and drag to look around.

Left-click a unit to select it.

Right-click a unit to have it move towards a space. Units are pretty dumb.

Shift + right-click to queue a move command.

Space to acknowledge the end of your turn.

Tab shows player names; press 1-6 while this is active to set your team.

## Mechanics

A "turn" is just a chunk of time during which units are allowed to operate, before the game pauses once again for new commands.
During this time, units can move and attack; they move to follow commands, and attack anything in range.
Note that a unit left idle will charge up its "attack" ability, followed by its "move" ability, meaning it can then do either instantly when necessary.

Archers have 2 tiles of range, but reload much slower.

Golems have 2 health, and will heal if they have nothing else to do.

Berserkers are quite dangerous; they move and attack slightly faster, can kill a Golem in one hit, and can push through a fatal wound long enough for one more hit. A well-placed Archer will still make short work of a Berserker, though.

Exploders can push through a fatal wound long enough to close with the enemy, making them effective against Archers. When they do die, they will hit everything around them, including allies.

## Saves

The game records all commands (except chat, and some other unimportant stuff) in a log. This also serves as the save system, since logs can be replayed.
New logs are gzipped by default, though a plain text file can also be loaded as a save.
On Linux, you can use the `gunzip` / `gzip` utilities to work with gzipped saves.

The game ships with some map(s) in `saves/`.
In game, you can press Ctrl+S to write out a save of the current state to `saves/saved.gz`.
Alternatively, when you exit the program, the current log will be saved in `saves/most_recent.gz`.
In either case, it is recommended to rename this if it's a save you care about, since it is overwritten each time.

A save can be loaded by specifying the path to it as the 4th arg (after port). This also marks you as the host, meaning when new players join you will automatically send them the log line-by-line to get them up to speed. See `/sync` in the Commands section, below.

## Commands

Most commands, listed in order of importance. There's a couple internal ones I omit for simplicity.
-   `/seats [name]...` sets the seats. This is more-or-less the teams, and determines which units you can control and who has to acknowledge before the turn continues.

    If, for instance, joe and sue are playing, enter `/seats joe sue`.

    Note that YOU MUST SET SEATS before anyone can control units.
-   `/callhash` - All clients will print a short hash of the game state, good for checking consistency.
-   `/host` - Marks yourself as host, and clears anyone else who was previously host. "host" just means you automatically /sync to new players.
-   `/dehost` - Marks yourself as *not* host; no effect if you weren't host.
-   `/sync [name]...` - Sends the current log as you know it to the named players, who will replay it. You usually won't need to do this manually so long as someone is `/host`. Some notes here:
    - If the new named players aren't starting from a fresh load, this will throw them off
    - There's some weirdness under the hood to support this; it should be pretty robust, but if you try to `/sync` while there's already a `/sync` going on, you'll probably have a bad time.
    - You know when the `/sync` is complete because the sender will automatically issue a `/callhash`.
- `/T [time]` - This is issued internally by the 'space' key, and says how many time units you're ready for the game to advance. Using this manually mostly just makes you a dick because nobody will know why that turn was 'short', with one exception - you can use `/T -1` to "unready" yourself. The default move is currently 360\*3 time units (3 swordsman moves) long.
- `/alliance <team> <allianceCode>` - Sets the specified team alliance code. Teams which have bitwise-and alliance codes not equal to 0 will not attack each other. Default alliance codes are 1<<(team).

### Editor commands

These are intended for use for map editing. Technically they're available at any time, but using them during a game would be impolite.

- Ctrl+E from the game window to toggle edit mode - currently there is no visual indicator, sadly. In this mode, click+drag paints and erases land instead of panning the view.
- Middle-click a tile to print its coordinates. This only shows in your output.
- `/e [x] [y] [type] [team]` - Creates an entity at the given location. Units will not have any abilities charged. Types:
  - "S" - [Swordsfighter](https://qwantz.com/index.php?comic=2460)
  - "A" - Archer
  - "B" - Berserker
  - "G" - Golem
  - "GRASS" and "rm" are used internaly by the edit-mode mouse; neither of these accepts a team.
- `/bias [team] [angle] [flip]` - Sets a bias, which applies to all units for that team spawned after this point. This only really matters if you want a *perfectly balanced* map.
  -   angle - What angle the unit spawns "facing", which affects e.g. preferred targets. This will be reset when it moves the first time.

      0 is to the right, 1 is just above that, etc, up to 5.
  -   flip - Affects e.g. which way to go around an obstacle (left or right). Must be 1 or -1.

If you want to save your work as a map, consider unzipping the log afterwards and cleaning up any accidental commands, e.g. removing and re-creating the same tile, to improve load speed. To this end, sorting the file (e.g. with the Unix `sort` util) might prove helpful, but it does re-order commands. Remember, there's no magic around save games; it just replays the log.
