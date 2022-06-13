import smtplib
from email.message import EmailMessage
from decouple import config


class Email:
    def __init__(self):
        self.sender = config('EMAIL_ADDRESS')
        self.email_pw = config('EMAIL_PASSWORD')
        self.port = config('EMAIL_PORT')
        self.smtp_domain = config('SMTP_DOMAIN')

    async def send_email(self, to, subject, message):
        msg = EmailMessage()
        msg.set_content(message)
        msg['From'] = self.sender
        msg['To'] = to
        msg['Subject'] = subject

        mailserver = smtplib.SMTP(self.smtp_domain, self.port)
        # identify ourselves to smtp gmail client
        mailserver.ehlo()
        # secure our email with tls encryption
        mailserver.starttls()
        # re-identify ourselves as an encrypted connection
        mailserver.ehlo()
        mailserver.login(self.sender, self.email_pw)

        mailserver.sendmail(self.sender, to, msg.as_string())

        mailserver.quit()

    def send_invite_email(self, code, email):
        # TODO Change localhost to configured domain url
        url = "localhost:8000/activate/" + code
        subject = "Welcome"
        message = "Click on the following link to activate your account. " + url
        self.send_email(email, subject, message)
