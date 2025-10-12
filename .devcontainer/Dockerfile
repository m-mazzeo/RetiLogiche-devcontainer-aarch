FROM mcr.microsoft.com/devcontainers/base:noble

ENV HOME=/home/vscode/

# asembler

RUN apt update && apt install -y gcc-multilib-i686-linux-gnu \
	binutils-i686-linux-gnu \
	binutils-i686-linux-gnu-dbg gdb-multiarch
RUN apt update && apt install -y qemu-user-static \
	libc6-i386-cross 
RUN apt update && apt install -y file tmux
# tmux
	
RUN ln -s $(find /usr/i686-linux-gnu/ -name ld-linux.so.2 | head -n 1) /lib/
RUN ln -s $(find /usr/i686-linux-gnu/ -name libc.so.6 | head -n 1) /lib/

# verilog

# - dipendenze
RUN apt update && apt install -y iverilog gtkwave

# Add the assemble and debug files
USER vscode

RUN mkdir $HOME/RETI

COPY ./bin $HOME/RETI/bin

RUN echo 'PATH=$HOME/RETI/bin:$PATH' >> $HOME/.bashrc

# mount the working dir

RUN mkdir $HOME/RETI/workdir
RUN chown -R vscode:vscode $HOME/RETI/workdir
WORKDIR $HOME/RETI/workdir
