import hashlib
import hmac
import jinja2
import os
import re
import webapp2
import json
import sys
import traceback

from google.appengine.api import users

from models.disciple import Disciple

from dictionary import Dictionary


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
            template_args = {
                             'user': user,
                             'login_href': users.create_logout_url('/'),
                             'login_content': 'Logout'}
            
            keys = self.request.get('keys')
            if keys:
                
                config = "?keys=%s" % keys
                if self.request.get('require'):
                    config += "&%s" % self.request.get('require')
                
                self.set_cookie('quiz_config', str(config))
                self.set_cookie('quiz_mode', 'WORD')    
            
            else:
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
                        
                isReview = (stage == 'review' or current_lesson == 1)
                
                config = '?unit=%d' % (current_lesson)
                if stage:
                    config += '&stage=%s' % stage
                    
                self.set_cookie('quiz_config', str(config))
                self.set_cookie('current_lesson', current_lesson)
                self.set_cookie('is_review', isReview)
                self.set_cookie('quiz_mode', 'KEY')
                
                template_args.update({
                    'current_lesson': current_lesson,
                    'is_review': isReview,
                    'lessonDescription': LESSONS[current_lesson - 1]["description"]
                })
                
            self.write_template('quiz.html', **template_args)
        else:
            self.redirect(users.create_login_url(self.request.uri))


    def post(self):
        user = users.get_current_user()
        #stage = self.request.get('stage')
        
        disciple = Disciple.get_current(user)
        disciple.tutor_max_lesson = int(self.request.get('current_lesson'))
        disciple.put()
        

class QuizData(BaseHandler):
    """In charge of querying the quiz data, with user-specific metadata attached"""
    def __init__(self,request=None, response=None):
        self.initialize(request, response)
        self.errorMsg = ''
        try:
            
            resources_directory = os.path.join(os.path.dirname(__file__), 'resources')
            dictfile = open(os.path.join(resources_directory, 'dict.json'), 'r')
            commonfile = open(os.path.join(resources_directory, 'common.json'), 'r') 
            conversionfile = open(os.path.join(resources_directory, 'binaryToSteno.json'), 'r')
            self.dictionary = Dictionary(json.load(dictfile), json.load(commonfile), json.load(conversionfile))
            dictfile.close()
            commonfile.close()
            conversionfile.close()
        except Exception as e:
            #"Printing only the traceback above the current stack frame"
            self.errorMsg += ''.join(traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2]))
            
            #"Printing the full traceback as if we had not caught it here..."
            self.errorMsg += self.format_exception(e)
    
    def format_exception(self, e):
        exception_list = traceback.format_stack()
        exception_list = exception_list[:-2]
        exception_list.extend(traceback.format_tb(sys.exc_info()[2]))
        exception_list.extend(traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1]))
    
        exception_str = "Traceback (most recent call last):\n"
        exception_str += "".join(exception_list)
        # Removing the last \n
        exception_str = exception_str[:-1]
    
        return exception_str
        
    def get(self):
        user = users.get_current_user()
        if user:
            if self.request.get('keys'):
                try:
                    filtered = self.dictionary.prepare_for_quiz(self.dictionary.filter(self.request.get('keys'), self.request.get('require')))
                    
                except Exception, e:
                    self.errorMsg += self.format_exception(e)
                
                if self.errorMsg is not '':
                    self.set_cookie('error', str(self.errorMsg))
                
                self.set_cookie('display_keys_in_prompt', False)    
            
                self.response.out.write(json.dumps(filtered))    
            elif self.request.get('unit'):
                material = self.get_material(int(self.request.get('unit')) - 1, self.request.get('stage') == 'review')
                self.response.out.write(material)
        else:
            self.redirect(users.create_login_url(self.request.uri))
            
    
    def get_material(self, unitIndex, isCumulative):
        stuff = LESSONS[unitIndex]["quiz"]
        if(isCumulative and unitIndex > 0):
            stuff = LESSONS[unitIndex]["quiz"]
            for i in reversed(range(0, unitIndex)):
                stuff = dict(stuff.items() + LESSONS[i]["quiz"].items())    
                    
        stuff = [int(i) for i in stuff.keys()]    
        return stuff;
    
app = webapp2.WSGIApplication([('/quiz/?', QuizPage),
                               ('/quiz/data', QuizData)], debug=True)
        
