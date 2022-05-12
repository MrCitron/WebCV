#!/usr/bin/env bash
set -e

GREEN='\033[0;32m'
NC='\033[0m'

function info {
    echo -e "${GREEN}${*}${NC}"
}

# Detect machine type
unameOut="$(uname -s)"
case "${unameOut}" in
    Linux*)     machine=Linux;;
    Darwin*)    machine=Mac;;
    CYGWIN*)    machine=Cygwin;;
    MINGW*)     machine=MinGw;;
    *)          machine="UNKNOWN:${unameOut}"
esac

# Create devhome dir and subdirs
if [ ! -d "${HOME}/devhome/projects" ];
then
    info Creating base directories
    mkdir -p ~/devhome/projects/perso
    mkdir -p ~/devhome/apps
fi

# Clone or update the dotfiles repository
TARGET_DIR="${HOME}/devhome/projects/perso/dotfiles"

if [ -d ${TARGET_DIR} ];
then
    info Pulling dotfiles repository
    cd ${TARGET_DIR}
    git checkout main
    git reset --hard origin/main -q
    cd - >> /dev/null
else
    info Cloning dotfiles repository into ${TARGET_DIR}
    git clone https://github.com/MrCitron/dotfiles.git ${TARGET_DIR}
fi

# Backup original .bashrc file if any
if [ ! -f ~/.bashrc.ori -a -f ~/.bashrc ];
then
    cp ~/.bashrc ~/.bashrc.ori
fi

# Init bash_profile on Mac or copy .bashrc on other machine types
if [ "${machine}" = "Mac" ];
then
    cp ${TARGET_DIR}/.bash_profile ~/.bash_profile
else
    if [ -f ~/.bashrc.ori ];
    then
        cp ~/.bashrc.ori ${TARGET_DIR}/.bashrc
    fi
fi

### START CUSTOMIZING ###
cat << EOF >> ${TARGET_DIR}/.bashrc

### START MOSMAN ###

source ${TARGET_DIR}/rc_extensions/my.sh
source ${TARGET_DIR}/rc_extensions/bash_it.sh
source ${TARGET_DIR}/rc_extensions/k8s.sh
source ${TARGET_DIR}/rc_extensions/nvm.sh
source ${TARGET_DIR}/rc_extensions/${machine}/gcp.sh
source ${TARGET_DIR}/rc_extensions/${machine}/rvm.sh
EOF

## Add current user as sudoer with nopasswd
if [ "${machine}" = "Linux" ];
then
    sudo bash -c "cat << EOF > /etc/sudoers.d/$USER
$USER ALL=(ALL) NOPASSWD: ALL
EOF
chmod 0440 /etc/sudoers.d/$USER
visudo -c
"
fi

## Useful packages
if [ "${machine}" = "Mac" ];
then
    echo TODO brew install
else
    info Update system and install useful packages
    sudo apt-get -qq  update
    sudo apt-get -qqy upgrade
    sudo apt-get -qqy install vim net-tools zip unzip docker.io mlocate jq
    # Docker
    sudo usermod -aG docker $USER
    
    # Test if there is a GUI
    #ls /usr/share/xsessions/ &> /dev/null
    if [ x$DISPLAY != x ];
    then
        sudo apt-get -qqy install terminator meld
        sudo snap install code --classic
        sudo snap install intellij-idea-ultimate --classic
    fi
fi

## Install bash_it
if [ ! -d ~/.bash_it ];
then
    info Installing bash-it
    git clone --depth=1 https://github.com/Bash-it/bash-it.git ~/.bash_it
    ~/.bash_it/install.sh --silent --no-modify-config
fi

info Setup bash-it extensions
set +e
source ~/.bash_it/bash_it.sh
set -e

BASH_IT_COMP_LIST="@awscli @bash-it @brew @docker @docker-compose @gcloud @git @github-cli @history @kubectl @npm @nvm @pip @pip3 @ssh @system @terraform @vagrant"
bash-it search ${BASH_IT_COMP_LIST} --enable 

if [ "${machine}" = "Mac" ];
then
    BASH_IT_COMP_LIST_MACOS="@brew"
    bash-it enable plugin ${BASH_IT_COMP_LIST_MACOS} 
fi

## Install gcloud cli, kubectl and krew
if ! command -v gcloud &> /dev/null;
then
    info Setup gcloud, kubectl, k9s
    if [ "${machine}" = "Mac" ];
    then
        brew install gcloud kubectl k9s
    else
        sudo apt-get -qqy install apt-transport-https ca-certificates gnupg
        echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
        curl -sS https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
        sudo apt-get -qqy update
        sudo apt-get -qqy install google-cloud-cli kubectl
        curl -sS https://webinstall.dev/k9s | bash
    fi
    
    info Setup krew
    (
    cd "$(mktemp -d)" &&
    OS="$(uname | tr '[:upper:]' '[:lower:]')" &&
    ARCH="$(uname -m | sed -e 's/x86_64/amd64/' -e 's/\(arm\)\(64\)\?.*/\1\2/' -e 's/aarch64$/arm64/')" &&
    KREW="krew-${OS}_${ARCH}" &&
    curl -fsSLO "https://github.com/kubernetes-sigs/krew/releases/latest/download/${KREW}.tar.gz" &&
    tar zxvf "${KREW}.tar.gz" &&
    ./"${KREW}" install krew
    )
    export PATH="${KREW_ROOT:-$HOME/.krew}/bin:$PATH"
    kubectl krew install ns
    kubectl krew install ctx
fi

## Install nvm
if ! command -v nvm &> /dev/null;
then
    info Installing nvm
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh | PROFILE='/dev/null' bash
fi

## Install rvm
if ! command -v rvm &> /dev/null;
then
    if [ "${machine}" = "Mac" ];
    then
        echo todo
    else
        sudo apt-get -qqy install software-properties-common
        sudo apt-add-repository -y ppa:rael-gc/rvm
        sudo apt-get -qqy update
        sudo apt-get -qqy install rvm
        sudo usermod -a -G rvm $USER
    fi
fi

### Finishing customization
if [ "${machine}" = "Mac" ];
then
    cat << EOF >> ${TARGET_DIR}/.bashrc

export BASH_SILENCE_DEPRECATION_WARNING=1
[[ -r "/usr/local/etc/profile.d/bash_completion.sh" ]] && . "/usr/local/etc/profile.d/bash_completion.sh"
EOF
fi

cat << EOF >> ${TARGET_DIR}/.bashrc

### END   MOSMAN ###
EOF

# Link home dotfiles to the customized ones
for dotfile in .bashrc .gitconfig;
do
    ln -sf ${TARGET_DIR}/${dotfile} ~/${dotfile}
done

echo -n
info Logout or open a new shell to apply all changes