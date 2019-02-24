from json import dumps, loads
from sqlalchemy.orm import class_mapper
from flask import Flask, jsonify
from flask.views import MethodView
from fetch_gmail import DbServices, Utils, MailServices
from flask import request

app = Flask(__name__)
db_service = DbServices(labels=[], messages=[], mail_services=None)
mail_service = MailServices(user_id="me")
mail_service.auth_account()

FIELDS = [
    "from_email",
    "subject",
    "snippet",
    "datetime"
]
PROPERTIES = [
    "contains",
    "does_not_contains",
    "equals",
    "not_equals",

    "lt_day",
    "gt_day",
    "lt_month",
    "gt_month"
]
PREDICATE = [
    "all",
    "any",
]
ACTIONS = (
    "mark_as_unread",
    "mark_as_read",
    "move_message",
)

RULE_FIELD_PROPS = {
    "rules": [
        {
            "fields": [FIELDS[0], FIELDS[1], FIELDS[2]],
            "properties": [PROPERTIES[0], PROPERTIES[1], PROPERTIES[2], PROPERTIES[3]]
        },
        {
            "fields": [FIELDS[3]],
            "properties": [PROPERTIES[4], PROPERTIES[5], PROPERTIES[6], PROPERTIES[7]]
        }
    ],
    "actions":ACTIONS,
    "predicate":PREDICATE
}

VALIDATION_RULE = {
    "predicate_type": {
        "one_of": ["any", "all"],
        "type": str
    },
    "predicates": {
        "type": list,
        "item": {
            "field": {
                "type": str
            },
            "property": {
                "type": str
            },
            "value": {
                "type": str
            },
        }
    },
    "actions": {
        "type": list,
        "item": {
            "action": {
                "type": str
            },
            "value": {
                "type": str
            },
        }
    }
}


class MailApi(MethodView):

    def is_action_valid(self, data):
        dataDict = data
        data_keys = data.keys()
        val_rule = VALIDATION_RULE
        val_rule_keys = val_rule.keys()
        level_one_check = all(
            [val in data_keys for val in val_rule_keys])
        if not level_one_check:
            return jsonify({
                "error": "payload must contain %s" % (", ".join(val_rule_keys))
            }), 400

        if dataDict['predicate_type'] not in PREDICATE:
            return jsonify({
                "error": "predicates must contain proper value for predicate_type"
            }), 400

        # check all predicate
        for key, val in enumerate(dataDict['predicates']):
            pre_field = self.get_field(val.get('field', None))
            pre_property = self.get_properties(val.get('property', None))
            pre_value = val.get('value', None)
            if val.get('field') == "datetime":
                pre_value = Utils.get_int_or_none(val.get('value', None))
                dataDict['predicates'][key]['value'] = pre_value
            if None in [pre_field, pre_property, pre_value]:
                return jsonify({
                    "error": "predicates must contain proper value for field, property, value"
                }), 400

        # check all actions
        for val in dataDict['actions']:
            pre_action = self.get_action(val.get('action', None))
            labels = db_service.get_all_label_names()
            if pre_action == "move_message":
                pre_value = val.get('value', None)
                if pre_value not in labels:
                    return jsonify({
                        "error": "Actions: provide a valid vlue `label name` eg, INBOX"
                    }), 400
            if not pre_action:
                return jsonify({
                    "error": "Actions: must contain proper value for action"
                }), 400
        return True

    def get_action(self, data):
        if data in ACTIONS:
            return data

    def get_predicate(self, data):
        if data in PREDICATE:
            return data

    def get_properties(self, data):
        if data in PROPERTIES:
            return PROPERTIES

    def get_field(self, data):
        if data in FIELDS:
            return FIELDS

    def get(self):
        data = db_service.fetch_serialize_mails()
        return jsonify({"data": data})

    def post(self):
        dataDict = loads(request.data)
        validation_error = self.is_action_valid(dataDict)
        if validation_error is not True:
            return validation_error
        predicate_matching = db_service.get_mail_based_on_conditon(
            dataDict['predicate_type'], dataDict['predicates'])
        # perform actions
        md_data_ids = []
        for action in dataDict['actions']:
            if action['action'] == 'mark_as_unread':
                md_data = mail_service.switch_make_read_or_unread(
                    messages=predicate_matching, msg_action="unread")
            elif action['action'] == 'mark_as_read':
                md_data = mail_service.switch_make_read_or_unread(
                    messages=predicate_matching, msg_action="read")
            elif action['action'] == 'move_message':
                md_data = mail_service.move_messages(
                    messages=predicate_matching, to_lable=action['value'])
            md_data_ids += md_data
        # update modified data to database
        final_data = []
        if md_data_ids:
            final_data = db_service.get_mail_by_ids(
                ids=tuple(set(md_data_ids)))
            final_data = db_service.fetch_serialize_mails(mails=final_data)
        return jsonify({"md_data": final_data})


class ActionRules(MethodView):

    def get(self):
        return jsonify({"data": RULE_FIELD_PROPS})


class Labels(MethodView):

    def get(self):
        labels = db_service.get_all_label_names()
        return jsonify({"data": labels})


app.add_url_rule('/api/email', view_func=MailApi.as_view('Email'))
app.add_url_rule('/api/rules', view_func=ActionRules.as_view('Rules'))
app.add_url_rule('/api/labels', view_func=Labels.as_view('Labels'))

if __name__ == '__main__':
    app.run(debug=True)
