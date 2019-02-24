import email
import base64
from apiclient import errors
import pickle
import os.path
from dateutil.parser import parse
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from apiclient import errors
from sqlalchemy import create_engine
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import class_mapper
from sqlalchemy import or_, and_, func

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify'
]
engine = create_engine('sqlite:///maildb.db')
Base = declarative_base()
DBSession = sessionmaker(bind=engine)
session = DBSession()


class Label(Base):
    __tablename__ = 'email_label'
    id = Column('label_id', Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    label_type = Column(String(50), nullable=False)
    message_list_visibility = Column(String(50), nullable=True)
    label_list_visibility = Column(String(50), nullable=True)


class EmailId(Base):
    __tablename__ = 'emailid'
    id = Column('emailid_id', Integer, primary_key=True)
    name = Column(String(70), nullable=True)
    email = Column(String(100), nullable=False)


class Email(Base):
    __tablename__ = 'email'
    id = Column('email_id', Integer, primary_key=True)
    email_ref_id = Column(String(100), nullable=True)
    snippet = Column(String(500), nullable=True)
    subject = Column(String(100), nullable=True)
    datetime = Column(DateTime, nullable=True)
    label = Column(String(150), nullable=True)

    from_email_id = Column(Integer, ForeignKey(EmailId.id))
    to_email_id = Column(Integer, ForeignKey(EmailId.id))

    from_email = relationship("EmailId", uselist=False,
                              foreign_keys=[from_email_id])
    to_email = relationship("EmailId", uselist=False,
                            foreign_keys=[to_email_id])


class Utils:
    @staticmethod
    def parse_time(s):
        try:
            ret = parse(s)
        except ValueError:
            ret = datetime.utcfromtimestamp(s)
        except:
            ret = None
        return ret

    @staticmethod
    def get_int_or_none(number):
        try:
            return int(number)
        except:
            return None


class MailServices:
    service = None

    def __init__(self, **kargs):
        self.user_id = kargs['user_id']

    def auth_account(self):
        creds = None
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server()
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        self.service = build('gmail', 'v1', credentials=creds)
        return self.service

    def list_messages_with_labels(self, label_ids=[], fetch_all=False):
        print("fetching mail index..")
        if fetch_all == False:
            print(
                "`fetch all data` is disabled, if you wish to fetch all data enable"
                " it in `list_messages_with_labels` function call"
            )
        try:
            response = self.service.users().messages().list(userId=self.user_id,
                                                            labelIds=label_ids).execute()
            messages = []
            if 'messages' in response:
                messages.extend(response['messages'])

            if fetch_all:
                while 'nextPageToken' in response:
                    page_token = response['nextPageToken']
                    response = self.service.users().messages().list(userId=self.user_id,
                                                                    labelIds=label_ids,
                                                                    pageToken=page_token).execute()
                    messages.extend(response['messages'])

            return messages
        except errors.HttpError as error:
            print('An error occurred: %s' % error)

    def modify_message(self, msg_id, msg_labels):
        try:
            message = self.service.users().messages().modify(userId=self.user_id, id=msg_id,
                                                             body=msg_labels).execute()

            label_ids = message['labelIds']

            print('Message ID: %s - With Label IDs %s' % (msg_id, label_ids))
            return message
        except errors.HttpError as error:
            print('An error occurred: %s' % error)

    def create_msg_labels(self, labels_to_remove=[], labels_to_add=[]):
        return {'removeLabelIds': labels_to_remove, 'addLabelIds': labels_to_add}

    def switch_make_read_or_unread(self, messages=[], msg_action="read"):
        md_data_ids = []
        email_mappings = []
        for message in messages:
            if msg_action == "read":
                action_data = self.create_msg_labels(
                    labels_to_remove=["UNREAD"])
            elif msg_action == "unread":
                action_data = self.create_msg_labels(labels_to_add=["UNREAD"])
            md_data = self.modify_message(message.email_ref_id, action_data)
            if md_data:
                md_data_ids.append(message.id)
                email_mappings.append(
                    {"label": ",".join(md_data['labelIds']), "id": message.id})
        if md_data:
            session.bulk_update_mappings(Email, email_mappings)
            session.commit()
        return md_data_ids

    def move_messages(self, to_lable, messages=[]):
        md_data_ids = []
        email_mappings = []
        for message in messages:
            action_data = self.create_msg_labels(labels_to_add=[to_lable])
            md_data = self.modify_message(message.email_ref_id, action_data)
            if md_data:
                md_data_ids.append(message.id)
                email_mappings.append(
                    {"id": message.id, "label": ",".join(md_data['labelIds'])})
        if md_data:
            session.bulk_update_mappings(Email, email_mappings)
            session.commit()
        return md_data_ids

    def list_labels(self):
        print("fetching labels ..")
        try:
            response = self.service.users().labels().list(userId=self.user_id).execute()
            labels = response['labels']
            return labels
        except errors.HttpError as error:
            print('An error occurred: %s' % error)

    def get_message(self, msg_id):
        try:
            message = self.service.users().messages().get(
                userId=self.user_id, id=msg_id).execute()
            return message
        except errors.HttpError as error:
            print('An error occurred: %s' % error)

    def extract_basic_message_details(self, headers):
        to_extract = ["To", "From", "Date", "Subject"]
        data = {"From": "", "Date": "", "Subject": "", "To": ""}
        for header in headers:
            if header['name'] in to_extract:
                data[header['name']] = header['value']
        return data

    def get_preprocessed_message(self, messages):
        pre_messages = []
        emails = []
        for message in messages:
            message = self.get_message(message['id'])
            if message:
                ext_data = self.extract_basic_message_details(
                    message['payload']['headers'])
                data = {
                    'id': message['id'],
                    'labels': message['labelIds'],
                    'snippet': message['snippet'],
                    'to_email': ext_data.get('To'),
                    'from_email': ext_data.get('From'),
                    'subject': ext_data.get('Subject'),
                    'date': ext_data.get('Date'),
                }
                emails.append(ext_data.get('To'))
                emails.append(ext_data.get('From'))
                pre_messages.append(data)
        return pre_messages, emails


class DbServices:

    def __init__(self, **kargs):
        self.labels = kargs.get('labels', [])
        self.messages = kargs.get('messages', [])
        self.mail_services = kargs.get('mail_services')

    def get_all_lables(self):
        return session.query(Label).all()

    def get_all_label_names(self):
        labels = self.get_all_lables()
        return [label.name for label in labels]

    def get_all_email_ids(self):
        emails = session.query(EmailId).all()
        return [email.email for email in emails]

    def get_mail_by_id(self, data_id):
        return session.query(Email).filter_by(email_ref_id=data_id).first()

    def get_mail_by_ids(self, ids):
        return session.query(Email).filter(Email.id.in_(ids)).all()

    def get_all_email_identifier(self):
        mails = session.query(Email).all()
        return [mail.email_ref_id for mail in mails]

    def mail_id_by_mailid(self, email_id):
        return session.query(EmailId).filter_by(email=email_id).first()

    def get_label_by_name(self, label_name):
        return session.query(Label).filter_by(name=label_name).first()

    def fetch_serialize_mails(self, mails=[]):
        if not mails:
            mails = session.query(Email).all()
        serialized = [
            self.mail_serialize(email)
            for email in mails
        ]
        return serialized

    def get_mail_based_on_conditon(self, condition, predicated):
        field_map = {
            "from_email": Email.from_email,
            "subject": Email.subject,
            "snippet": Email.snippet,
            "datetime": Email.datetime
        }
        if condition == "any":
            condition_fil = or_
        elif condition == "all":
            condition_fil = and_

        conditions = []
        for pre in predicated:
            if pre['field'] == "datetime":
                value = pre['value']
                if pre['property'] == "lt_day":
                    d = datetime.now() - timedelta(days=value)
                    conditions.append(field_map[pre['field']] <= d)
                elif pre['property'] == "gt_day":
                    d = datetime.now() - timedelta(days=value)
                    conditions.append(field_map[pre['field']] >= d)
                elif pre['property'] == "lt_month":
                    d = datetime.now() - timedelta(days=value*28)
                    conditions.append(field_map[pre['field']] <= d)
                elif pre['property'] == "gt_month":
                    d = datetime.now() - timedelta(days=value*28)
                    conditions.append(field_map[pre['field']] >= d)
            else:
                if pre['property'] == "contains":
                    conditions.append(
                        field_map[pre['field']].contains('%'+pre['value']+'%'))
                elif pre['property'] == "does_not_contains":
                    conditions.append(
                        ~field_map[pre['field']].contains('%'+pre['value']+'%'))
                elif pre['property'] == "equals":
                    conditions.append(func.lower(
                        field_map[pre['field']]) == func.lower(pre['value']))
                elif pre['property'] == "not_equals":
                    conditions.append(func.lower(
                        field_map[pre['field']]) != func.lower(pre['value']))
        data = session.query(Email).filter(condition_fil(*conditions)).all()
        for val in data:
            print(val.subject)
        return data

    def mail_serialize(self, model):
        return {
            "id": model.id,
            "email_ref_id": model.email_ref_id,
            "snippet": model.snippet,
            "subject": model.subject,
            "datetime": str(model.datetime),
            "from_email": model.from_email.email,
            "to_email": model.to_email.email,
            "label": model.label.split(",") if model.label else [],
        }

    def store_labels(self):
        print("storing labels to db..")
        ex_labels = self.get_all_label_names()
        label_objects = []
        for label in self.labels:
            if label['name'] not in ex_labels:
                label_obj = Label(
                    name=label['name'],
                    label_type=label.get('labelType', ''),
                    message_list_visibility=label.get(
                        'messageListVisibility', ''),
                    label_list_visibility=label.get(
                        'labelListVisibility', ''),
                )
                label_objects.append(label_obj)
        if label_objects:
            session.bulk_save_objects(label_objects)
            session.commit()

    def process_mail_id(self, email):
        email = email.replace(">", '').split("<")
        if len(email) == 1 and email[0].strip():
            return email[0].strip()
        elif len(email) > 1 and email[0].strip():
            return email[1].strip()

    def preprocess_emails(self, emails):
        pr_emails = {}
        for email in emails:
            email = email.replace(">", '').split("<")
            if len(email) == 1 and email[0].strip():
                email_id = email[0].strip()
                if not pr_emails.get(email_id):
                    pr_emails[email_id] = {}
                pr_emails[email_id]['email'] = email_id
            elif len(email) > 1 and email[0].strip():
                email_id = email[1].strip()
                name = email[0].strip()
                if not pr_emails.get(email_id):
                    pr_emails[email_id] = {}
                pr_emails[email_id]['email'] = email_id
                if name:
                    pr_emails[email_id]['name'] = name.replace('"', "")
        return pr_emails

    def store_email_id_and_fetch_messages(self):
        print("Fetching mail data ..")
        print("This may take a while pls wait..")
        messages, emails = self.mail_services.get_preprocessed_message(
            self.messages)
        pre_emails = self.preprocess_emails(emails)
        ex_email_ids = self.get_all_email_ids()
        email_objects = []
        print("storing email ids to db..")
        for key, item in pre_emails.items():
            if item['email'] not in ex_email_ids:
                email_obj = EmailId(
                    name=item.get('name'),
                    email=item['email'],
                )
                email_objects.append(email_obj)
        if email_objects:
            session.bulk_save_objects(email_objects)
            session.commit()
        return messages

    def store_emails(self, messages):
        print("storing mails to db..")
        email_red_ids = self.get_all_email_identifier()
        mail_objects = []
        for message in messages:
            if message['id'] not in messages:
                from_email = self.mail_id_by_mailid(
                    self.process_mail_id(message['from_email']))
                to_email = self.mail_id_by_mailid(
                    self.process_mail_id(message['to_email']))
                label = ",".join(message['labels'])
                if not from_email or not to_email:
                    continue
                mail_obj = Email(
                    email_ref_id=message['id'],
                    snippet=message['snippet'],
                    subject=message['subject'],
                    datetime=Utils.parse_time(message['date']),
                    from_email_id=from_email.id,
                    to_email_id=to_email.id,
                    label=label
                )
                mail_objects.append(mail_obj)
        if mail_objects:
            session.bulk_save_objects(mail_objects)
            session.commit()

    def update_mail_labels(self, messages=[]):
        pass

    def store_data(self):
        self.store_labels()
        messages = self.store_email_id_and_fetch_messages()
        self.store_emails(messages)


def main():
    Base.metadata.create_all(engine)
    service = MailServices(user_id="me")
    if service.auth_account():
        labels = service.list_labels()
        messages = service.list_messages_with_labels(fetch_all=False)
        db_services = DbServices(
            labels=labels, messages=messages, mail_services=service)
        db_services.store_data()
        print("all good done.")


if __name__ == '__main__':
    main()
