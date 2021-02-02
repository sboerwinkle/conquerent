CONQUERENT
==========

A shitty strategy game for 0-6 players. Right now it's not even so much a game tbh

Requirements
------------

At the moment this only runs on Linux, but that might change in the future since it's primarily Python

- Bash
- python3
- pygame

Server
------

The server is extremely dumb. It accepts TCP connections on a port (specified as an optional argument, and the only argument), and then echoes any messages it gets to everyone on the server. This includes the person who sent the message, which is actually kinda nice so everyone gets a consistent order. You could use it for other things theoretically.

Anyway, launch that first. Since the server doesn't manage any game logic, there's no such thing as a "private" game beyond what your firewall or general anonymity can provide.

Client
------

The client is best invoked from game.sh, which accepts 3 arguments: name, host, and port. "name" must be unique among clients, and should probably just be letters, but I think technically anything satisfying the regex `[^#: ][^: ]*` *should* work.

### Output

The first time you run game.sh you'll get a screed about the `output-script`. Read it, I'm not repeating myself here - I promise it's not difficult setup.

### Input

Some commands can only be entered via the console (the terminal window where you launched the game). Of these, the most important are:
-   Anything without a leading `/` is chat
-   `/seats [name]...` sets the seats. This is more-or-less the teams, and determines which units you can control and who has to acknowledge before the turn continues.

    If, for instance, joe and sue are playing, enter `/seats joe sue`.

### Controls

Left-click a unit to select it.

Right-click a unit to have it move towards a space. Units are pretty dumb.

Shift + right-click to queue a move command.

Right now you can't attack, hence the unplayability :)

Space to acknowledge the end of your turn.

### Saves

The game records all commands (except chat, and some other unimportant stuff) in a log. This also serves as the save system, since logs can be replayed. Logs are gzipped; Use gunzip / gzip if you want to view them.

When you exit the program, the current log will be saved in `saves/most_recent.gz`. Rename this if you want it to stick around! If you wish to load a save, specify the path to it as the 4th arg (after port) - if it's found successfully, the game should restore to that state. This also marks you as the host, meaning when new players join you will automatically send them the log line-by-line to get them up to speed. See `/sync` in the Commands section, below.

### Commands

Some other useful commands that can be entered at the console:
- `/callhash` - All clients will print a short hash of the game state, good for checking consistency.
- `/host` - Marks yourself as host, and clears anyone else who was previously host. "host" just means you automatically /sync to new players.
- `/sync [name]...` - Sends the current log as you know it to the named players, who will replay it. Some notes here:
  - If the new named players aren't starting from a fresh load, this will throw them off
  - There's some weirdness under the hood to support this; it should be pretty robust, but if you try to `/sync` while there's already a `/sync` going on, you'll probably have a bad time.
  - You know when the `/sync` is complete because the sender will automatically issue a `/callhash`.
- `/team [team]...` - Changes which teams you can control. Numbering starts from 0.
- `/seats [name]...` - As previously mentioned, this sets the seats. This also (re)sets teams for everyone, e.g. first seat gets team 0.
- `/T [time]` - This is issued internally by the 'space' key, and says how many time units you're ready for the game to advance. Using this manually mostly just makes you a dick because nobody will know why that turn was 'short', with one exception - you can use `/T -1` to "unready" yourself.
