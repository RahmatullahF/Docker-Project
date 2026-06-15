terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
      version = "6.47.0"
    }
  }
}

provider "aws" {
  # Configuration options
  region = "us-east-1"
}

resource "aws_instance" "tf-docker-ec2" {
    ami = "ami-084568db4383264d4"
    instance_type = "t3.micro"
    key_name = "Techpro-key"
    vpc_security_group_ids = [aws_security_group.my-security-group.id]
    tags = {
        Name = "TechPro Web Server"
    }
    user_data = <<-EOF
          #! /bin/bash
          curl -fsSL https://get.docker.com -o get-docker.sh
          sh get-docker.sh
          sudo groupadd docker
          sudo usermod -aG docker ubuntu
          newgrp docker
          cd /home/ubuntu
          git clone https://github.com/RahmatullahF/Docker-Project.git
          cd /home/ubuntu/Docker-Project
          docker compose up -d
          docker ps -a
          EOF 
    }

locals {
  secgr-dynamic-ports = [22,80,443,8000,5000]
  user= "techpro"
}

resource "aws_security_group" "my-security-group" {
  name        = "${local.user}-docker-instance-sg"
  description = "Allow SSH inbound traffic"
  dynamic "ingress" {
    for_each = local.secgr-dynamic-ports
    content {
      from_port = ingress.value
      to_port = ingress.value
      protocol = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
  }
}
  egress {
    description = "Outbound Allowed"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

output "name" {
  value= "http://${aws_instance.tf-docker-ec2.public_ip}"
}
