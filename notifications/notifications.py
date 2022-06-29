from database_models.models import DBNotification, NotificationPriority
from database_models.db_connector import get_database


class Notification:

    def __init__(self):
        self.db = get_database()

    def send(self, recipient_id, message, expiration, priority=NotificationPriority.normal):
        notification = DBNotification(recipient_user_id=recipient_id, message=message, priority=priority,
                                      expiration=expiration)
        self.db.add(notification)
        self.db.commit()
