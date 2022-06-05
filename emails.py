import smtplib
import os
from email.message import EmailMessage

class Email:
    def __init__(self):
        self.sender = 'bandfinderapp@gmail.com'
        self.email_pw = os.environ['email_pw']
        self.port = 587
        self.smtp_domain = "smtp.gmail.com"

    async def send_email(self, to, subject, message):
        msg = EmailMessage()
        msg.set_content(message)
        msg['From'] = self.sender
        msg['To'] = to
        msg['Subject'] = subject

        mailserver = smtplib.SMTP('smtp.gmail.com',self.port)
        # identify ourselves to smtp gmail client
        mailserver.ehlo()
        # secure our email with tls encryption
        mailserver.starttls()
        # re-identify ourselves as an encrypted connection
        mailserver.ehlo()
        mailserver.login(self.sender, self.email_pw)

        mailserver.sendmail(self.sender,to,msg.as_string())

        mailserver.quit()

    def send_invite_email(self, code, email):
        url = "localhost:8000/activate/" + code
        subject = "Welcome"
        message = "Click on the following link to activate your account. " + url
        self.send_email(email,subject,message)
