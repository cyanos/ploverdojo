import hashlib
import hmac
import jinja2
import os
import re
import webapp2
import json

from google.appengine.api import users

from models.disciple import Disciple


template_directory = os.path.join(os.path.dirname(__file__), 'templates')
jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(template_directory), autoescape=True)


hmac_message = os.path.join(os.path.dirname(__file__), 'secret/message')
f = open(hmac_message, 'r')
SECRET = f.read().strip()
f.close()

# todo: lessons/keyboard.json is obsolete. refactor to pull assets/tutorLessons.json in quiz.js
l = open(os.path.join(os.path.dirname(__file__), 'lessons/keyboard.json'), 'r')
LESSONS = json.load(l)
l.close()

def render_template(template, **template_values):
    """Renders the given template with the given template_values"""
    # retrieve the html template
    t = jinja_environment.get_template(template)

    # render the html template with th given dictionary
    return t.render(template_values)


def create_salt():
    return hashlib.sha256(os.urandom(16)).hexdigest()


def create_salt_hash_pair(input, salt=None):
    if not salt:
        salt = create_salt()
    hash = hmac.new(SECRET, salt + input, hashlib.sha256).hexdigest()
    return "%s|%s" % (salt, hash)


def validate_salt_hash_pair(input, hash):
    salt = hash.split('|')[0]
    return hash == create_salt_hash_pair(input, salt)


def create_value_salt_hash_triplet(value, salt=None):
    if not salt:
        salt = create_salt()
    hash = hmac.new(SECRET, str(value) + salt).hexdigest()
    return "%s|%s|%s" % (value, salt, hash)


def validate_value_salt_hash_triplet(hash):
    value = hash.split('|')[0]
    salt = hash.split('|')[1]
    if hash == create_value_salt_hash_triplet(value, salt):
        return value


class BaseHandler(webapp2.RequestHandler):
    """Represents a handler which contains functions necessary for multiple
    handlers"""
    def write_template(self, template, **template_values):
        """Function to write out the given template with the given
        template_values"""
        self.response.out.write(render_template(template, **template_values))

    def set_cookie(self, name, value):
        """Function to set an http cookie"""
        self.response.headers.add_header('Set-Cookie', '%s=%s; Path=/' % (name, value))

    def get_cookie(self, name):
        """Function to get the value of a named parameter of an http cookie"""
        return self.request.cookies.get(name)

    def set_encrypted_cookie(self, name, value):
        """Function to set an http cookie"""
        self.response.headers.add_header('Set-Cookie', '%s=%s; Path=/' % (name, create_value_salt_hash_triplet(value)))

    def get_encrypted_cookie(self, name):
        """Function to get the value of a named parameter of an http cookie"""
        return validate_value_salt_hash_triplet(self.request.cookies.get(name))


class QuizPage(BaseHandler):
    def get(self):
        user = users.get_current_user()
        if user:
           stage = self.request.get('stage')
           current_lesson = 1
           # unit number from the URL should override that from the database
           if(self.request.get('unit')):
               current_lesson = int(self.request.get('unit'))
               if(current_lesson >= len(LESSONS)):
                   current_lesson = 1
           else:
               disciple = Disciple.get_current(user)
               if(disciple and hasattr(disciple, 'tutor_max_lesson') and disciple.tutor_max_lesson):
                   current_lesson = int(disciple.tutor_max_lesson)
           material = self.get_material(current_lesson - 1, stage == 'review')
           isReview = (stage == 'review' or current_lesson == 1)
           self.set_cookie('testdata', json.dumps(material))
           self.set_cookie('current_lesson', current_lesson)
           self.set_cookie('is_review', isReview )
           self.write_template('quiz.html', **{
               'user': user,
               'current_lesson': current_lesson,
               'is_review': isReview,
               'lessonDescription': LESSONS[current_lesson -1]["description"],
               'login_href': users.create_logout_url(self.request.uri),
               'login_content': 'Logout'
           })
        else:
            self.redirect(users.create_login_url(self.request.uri))

    def get_material(self, unitIndex, isCumulative):
        if(isCumulative and unitIndex > 0):
            stuff = LESSONS[unitIndex]["quiz"]
            for i in reversed(range(0, unitIndex)):
                stuff = dict(stuff.items() + LESSONS[i]["quiz"].items())
            return stuff
            
        return LESSONS[unitIndex]["quiz"];

    def post(self):
        user = users.get_current_user()
        #stage = self.request.get('stage')
        
        disciple = Disciple.get_current(user)
        disciple.tutor_max_lesson = int(self.request.get('current_lesson'))
        disciple.put()
        
    
app = webapp2.WSGIApplication([('/quiz/?', QuizPage)], debug=True)
        