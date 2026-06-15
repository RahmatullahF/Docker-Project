Car Rental System 🚗

This project provides a modern car rental platform. It is a professional web application developed using the Flask framework and deployed with Nginx and Gunicorn.

🌟 Features
👥 User Operations

User registration and login

Profile editing

Password reset

Email verification

🚙 Vehicle Operations

Vehicle listing and advanced search

Filtering by brand, model, year, and price

Vehicle detail view

Car rental and reservation

📊 Admin Panel

Statistics dashboard

Total number of vehicles

Number of users

Number of rentals

Total revenue

Vehicle management

User management

Rental tracking

🛠️ Technologies

Backend: Python Flask

Frontend: HTML, CSS, JavaScript

Database: MySQL

Web Server: Nginx

WSGI Server: Gunicorn

Deployment: Ubuntu Server

📋 Requirements
python3
python3-venv
mysql-server
nginx

🚀 Installation

Clone the repository:

git clone https://github.com/username/car-rental.git
cd car-rental


Set environment variables:

cp .env.example .env
# Edit the .env file


Create a virtual environment:

python3 -m venv venv
source venv/bin/activate


Install dependencies:

pip install -r requirements.txt


Create the database:

mysql -u root -p
CREATE DATABASE car_rental;


Start the application:

./deploy.sh

🔧 Deployment

Required deployment files:

1. Nginx Configuration
server {
    listen 80;
    server_name your_domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

2. Gunicorn Service File
[Unit]
Description=Gunicorn instance for car rental app
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/path/to/app
ExecStart=/path/to/venv/bin/gunicorn --workers 4 wsgi:app

[Install]
WantedBy=multi-user.target

📝 Usage

/register – New user registration

/login – User login

/search – Vehicle search

/profile – Profile management

/statistics – Admin statistics

👥 Roles
Regular User

Search and view vehicles

Rent a vehicle

Edit profile

Admin

All regular user permissions

View statistics

Manage vehicles and users

🔒 Security

Password hashing

SQL injection protection

XSS protection

CSRF protection

Rate limiting

📈 Performance

Nginx reverse proxy

Gunicorn multi-worker setup

Database indexing

Static file caching

🤝 Contributing

Fork the repository

Create a feature branch

Commit your changes

Push your branch

Open a pull request

📄 License

This project is licensed under the MIT License. See the LICENSE
 file for details.

📞 Contact

Website: www.techprodevops.com

Email: info@techprodevops.com

🙏 Acknowledgements

Thanks to everyone who contributed to this project!