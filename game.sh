#!/bin/bash

if ! [ -e output_script ]; then
	echo "It looks like there's no output_script present."
	echo "This is intended to open a second window for viewing"
	echo "output, so it doesn't conflict with what you're"
	echo "typing."
	echo
	echo "If you don't care about all that, you can just put:"
	echo "------output_script------"
	echo "#!/bin/bash"
	echo "cat stdout_fifo"
	echo "-------------------------"
	echo
	echo "... but you're encouranged to use whatever termainal"
	echo "program you prefer. On a basic Ubuntu install, this"
	echo "works:"
	echo "------output_script------"
	echo "#!/bin/bash"
	echo 'gnome-terminal --working-directory=`pwd` -- cat stdout_fifo'
	echo "-------------------------"
	echo
	exit
fi
if ! [ -x output_script ]; then
	echo "output_script found but not executable."
	exit
fi

if [ $# -eq 3 ]; then
	rm -f stdout_fifo
	mkfifo stdout_fifo
	./output_script &
	./conquerent.py "$@" >stdout_fifo
	rm -f stdout_fifo
else
	echo $'Usage:\n'"$0 name host port"
fi;
