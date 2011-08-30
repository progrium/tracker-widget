from google.appengine.ext import webapp
from google.appengine.ext.webapp import util
from google.appengine.ext.webapp import template

from pytracker import Tracker
from pytracker import Story
from pytracker import HostedTrackerAuth

def stories_for_view(stories):
  return [dict(
    done=(s.current_state == 'accepted'),
    name=s.name,
    owner=(''.join([n[0] for n in s.owned_by.split(' ')]) if s.owned_by else ''),
    labels=(', '.join(list(s.labels))) if s.labels else '') 
    for s in stories]

class MainHandler(webapp.RequestHandler):
    def get(self):
        self.response.out.write('<pre>%s</pre>' % open('README').read())

class StoryWidgetHandler(webapp.RequestHandler):
    def get(self):
      css = self.request.get('css')
      username = self.request.get('username')
      password = self.request.get('password')
      project_id = self.request.get('project_id')
      filter = self.request.get('filter')
      
      auth = HostedTrackerAuth(username, password)
      project = Tracker(int(project_id), auth)
      stories = stories_for_view(project.GetStories(filter))
      
      self.response.out.write(template.render('widget.html', 
        {'stories': stories, 'css': css}))

class IterationWidgetHandler(webapp.RequestHandler):
    def get(self):
      css = self.request.get('css')
      username = self.request.get('username')
      password = self.request.get('password')
      project_id = self.request.get('project_id')
      iteration = self.request.get('iteration')
      
      auth = HostedTrackerAuth(username, password)
      project = Tracker(int(project_id), auth)
      stories = stories_for_view(project.GetIterationStories(iteration))
      
      self.response.out.write(template.render('widget.html', 
        {'stories': stories, 'css': css}))

def main():
    application = webapp.WSGIApplication([
      ('/', MainHandler),
      ('/widget/stories', StoryWidgetHandler),
      ('/widget/iteration', IterationWidgetHandler), ], debug=True)
    util.run_wsgi_app(application)


if __name__ == '__main__':
    main()
