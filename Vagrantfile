# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure(2) do |config|
    config.vm.box = "hashicorp/precise32"
    config.vm.provision :shell, path: "setup/bootstrap.sh"
    config.vm.network :forwarded_port, host: 8000, guest: 80



# For setting up heroku push
#   config.push.define "heroku" do |push|
#    push.app = "tranquil-oasis-6724"

end