#!/usr/bin/env python
#
# Copyright 2009 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""pytracker is a Python wrapper around the Tracker API."""

__author__ = 'dcoker@google.com (Doug Coker)'

import calendar
import cookielib
import re
import time
import urllib
import urllib2
import xml.dom
from xml.dom import minidom
import xml.parsers.expat
import xml.sax.saxutils

DEFAULT_BASE_API_URL = 'https://www.pivotaltracker.com/services/v2/'
# Some fields specify UTC, some GMT?
_TRACKER_DATETIME_RE = re.compile(r'^\d{4}/\d{2}/\d{2} .*(GMT|UTC)$')


def TrackerDatetimeToYMD(pdt):
  assert _TRACKER_DATETIME_RE.match(pdt)
  pdt = pdt.split()[0]
  pdt = pdt.replace('/', '-')
  return pdt


class Tracker(object):
  """Tracker API."""

  def __init__(self, project_id, auth,
               base_api_url=DEFAULT_BASE_API_URL):
    """Constructor.

    If you are debugging API calls, you may want to use a non-HTTPS API URL:
      base_api_url="http://www.pivotaltracker.com/services/v2/"

    Args:
      project_id: the Tracker ID (integer).
      auth: a TrackerAuth instance.
      base_api_url: the base URL of the HTTP API (with trailing /).
    """
    self.project_id = project_id
    self.base_api_url = base_api_url

    cookies = cookielib.CookieJar()
    self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookies))

    self.token = auth.EstablishAuthToken(self.opener)

  def _Api(self, request, method, body=None):
    url = self.base_api_url + 'projects/%d/%s' % (self.project_id,
                                                  request)

    headers = {}
    if self.token:
      headers['X-TrackerToken'] = self.token

    if not body and method == 'GET':
      # Do a GET
      req = urllib2.Request(url, None, headers)
    else:
      headers['Content-Type'] = 'application/xml'
      req = urllib2.Request(url, body, headers)
      req.get_method = lambda: method

    try:
      res = self.opener.open(req)
    except urllib2.HTTPError, e:
      message = "HTTP Status Code: %s\nMessage: %s\nURL: %s\nError: %s" % (e.code, e.msg, e.geturl(), e.read())
      raise TrackerApiException(message)

    return res.read()

  def _ApiQueryStories(self, query=None):
    if query:
      output = self._Api('stories?filter=' + urllib.quote_plus(query),
                         'GET')
    else:
      output = self._Api('stories', 'GET')

    # Hack: throw an exception if we didn't get valid XML.
    xml.parsers.expat.ParserCreate('utf-8').Parse(output, True)

    return output

  def GetStoriesXml(self):
    return self._ApiQueryStories()

  def GetReleaseStoriesXml(self):
    return self._ApiQueryStories('type:release')

  def GetIterationStories(self, iteration=None, offset=None, limit=None):
    iteration = ('/%s' % iteration) if iteration else ''
    params = []
    if offset:
      params.append('offset=%s' % urllib.quote_plus(str(offset)))
    if limit:
      params.append('limit=%s' % urllib.quote_plus(str(limit)))
      
    response = self._Api('iterations%s?%s' % (iteration, '&'.join(params)), 'GET')
    
    # Hack: throw an exception if we didn't get valid XML.
    xml.parsers.expat.ParserCreate('utf-8').Parse(response, True)
    
    parsed = xml.dom.minidom.parseString(response)
    els = parsed.getElementsByTagName('story')
    lst = []
    for el in els:
      lst.append(Story.FromXml(el.toxml()))
    return lst
    

  def GetStories(self, filt=None):
    """Fetch all Stories that satisfy the filter.

    Args:
      filt: a Tracker search filter.
    Returns:
      List of Story().
    """
    stories = self._ApiQueryStories(filt)
    parsed = xml.dom.minidom.parseString(stories)
    els = parsed.getElementsByTagName('story')
    lst = []
    for el in els:
      lst.append(Story.FromXml(el.toxml()))
    return lst

  def GetStory(self, story_id):
    story_xml = self._Api('stories/%d' % story_id, 'GET')
    return Story.FromXml(story_xml)

  def AddComment(self, story_id, comment):
    comment = '<note><text>%s</text></note>' % xml.sax.saxutils.escape(comment)
    self._Api('stories/%d/notes' % story_id, 'POST', comment)

  def AddNewStory(self, story):
    """Persists a new story to Tracker and returns the new Story."""
    story_xml = story.ToXml()
    res = self._Api('stories', 'POST', story_xml)
    story = Story.FromXml(res)
    return story

  def UpdateStoryById(self, story_id, story):
    """Persist changes to an existing story to Tracker.

    Use this method if you are changing a story without first retreiving the
    story.

    Args:
      story_id: The ID of the story to mutate
      story: The Story containing values to change.
    Returns:
      The updated Story().
    """
    story_xml = story.ToXml()
    res = self._Api('stories/%d' % story_id, 'PUT', story_xml)
    return Story.FromXml(res)

  def UpdateStory(self, story):
    """Persists changes to an existing story to Tracker.

    Use this method if you have a full Story object created by one of the query
    methods.

    Args:
      story: a Story()
    Returns:
      The updated Story().
    """
    story_xml = story.ToXml()
    res = self._Api('stories/%d' % story.GetStoryId(), 'PUT', story_xml)
    return Story.FromXml(res)

  def DeleteStory(self, story_id):
    """Deletes a story by story ID."""
    self._Api('stories/%d' % story_id, 'DELETE', '')


class TrackerAuth(object):
  """Abstract base class for establishing credentials for pytracker."""

  def __init__(self, username, password):
    self.username = username
    self.password = password

  def EstablishAuthToken(self, opener):
    """Returns the value for use as the X-TrackerToken HTTP header, or None.

    This method may mutate the cookie jar via opener.

    Args:
      opener: a urllib2.OpenerDirector instance that will be used for
              subsequent HTTP API calls.
    """
    raise NotImplementedError()


class TrackerAuthException(Exception):
  """Raised when something goes wrong with authentication."""


class NoTokensAvailableException(Exception):
  """Raised when HostedTrackerAuth can't find any tokens for this user."""


class TrackerApiException(Exception):
  """Raised when Tracker returns an error."""


class HostedTrackerAuth(TrackerAuth):
  """Authentication rules for hosted Tracker instances."""

  def EstablishAuthToken(self, opener):
    """Returns the first auth token returned by /services/tokens/active."""
    url = 'https://www.pivotaltracker.com/services/tokens/active'
    data = urllib.urlencode((('username', self.username),
                             ('password', self.password)))
    try:
      req = opener.open(url, data)
    except urllib2.HTTPError, e:
      if e.code == 404:
        raise NoTokensAvailableException(
            'Did you create any?  Check https://www.pivotaltracker.com/profile')
      else:
        raise

    res = req.read()

    dom = minidom.parseString(res)
    token = dom.getElementsByTagName('guid')[0].firstChild.data

    return token


class Story(object):
  """Represents a Story.

  This class can be used to represent a complete Story (generally queried from
  the Tracker class), or can contain partial information for update or create
  operations (constructed with default constructor).

  Internally, Story uses None to indicate that the client has not specified a
  value for the field or that it has not been parsed from XML.  This enables us
  to use the same Story object to define an update to multiple stories, without
  requiring that the client first fetch, parse, and update an existing story.
  This is supported by all mutable fields except for labels, which are
  represented by Tracker as a comma-separated list of strings in a single tag
  body.  For label operations on existing stories to be performed correctly,
  the Story must first be fetched from the server so that the existing labels
  are not lost.
  """

  # Fields that can be treated as strings when embedding in XML.
  UPDATE_FIELDS = ('story_type', 'current_state', 'name',
                   'description', 'estimate', 'requested_by', 'owned_by')

  # Type: immutable ints.
  story_id = None
  iteration_number = None

  # Type: immutable times (secs since epoch)
  created_at = None

  # Type: mutable time (secs since epoch)
  deadline = None

  # Type: mutable set (API methods expose as string)
  labels = None

  # Type: immutable strings
  url = None

  # Type: mutable strings
  requested_by = None
  owned_by = None
  story_type = None
  current_state = None
  description = None
  name = None
  estimate = None

  def __str__(self):
    return "Story(%r)" % self.__dict__

  @staticmethod
  def FromXml(as_xml):
    """Parses an XML string into a Story.

    Args:
      as_xml: a full XML document from the Tracker API.
    Returns:
      Story()
    """
    parsed = minidom.parseString(as_xml.encode('utf-8'))
    story = Story()
    story.story_id = int(parsed.getElementsByTagName('id')[0].firstChild.data)
    story.url = parsed.getElementsByTagName('url')[0].firstChild.data
    story.owned_by = Story._GetDataFromTag(parsed, 'owned_by')
    story.created_at = Story._ParseDatetimeIntoSecs(parsed, 'created_at')
    story.requested_by = Story._GetDataFromTag(parsed, 'requested_by')
    iteration = Story._GetDataFromTag(parsed, 'number')
    if iteration:
      story.iteration_number = int(iteration)

    story.SetStoryType(
        parsed.getElementsByTagName('story_type')[0].firstChild.data)
    story.SetCurrentState(
        parsed.getElementsByTagName('current_state')[0].firstChild.data)
    story.SetName(Story._GetDataFromTag(parsed, 'name'))
    story.SetDescription(Story._GetDataFromTag(parsed, 'description'))
    story.SetDeadline(Story._ParseDatetimeIntoSecs(parsed, 'deadline'))

    estimate = Story._GetDataFromTag(parsed, 'estimate')
    if estimate is not None:
        story.estimate = estimate
    labels = Story._GetDataFromTag(parsed, 'labels')
    if labels is not None:
      story.AddLabelsFromString(labels)

    return story

  @staticmethod
  def _GetDataFromTag(dom, tag):
    """Retrieve value associated with the tag, if any.

    Args:
      dom: XML DOM object
      tag: name of the desired tag

    Returns:
      None (if tag doesn't exist), empty string (if tag exists, but body is
      empty), or the tag body.
    """
    tags = dom.getElementsByTagName(tag)
    if not tags:
      return None
    elif tags[0].hasChildNodes():
      return tags[0].firstChild.data
    else:
      return ''

  @staticmethod
  def _ParseDatetimeIntoSecs(dom, tag):
    """Returns the tag body parsed into seconds-since-epoch."""
    el = dom.getElementsByTagName(tag)
    if not el:
      return None
    assert el[0].getAttribute('type') == 'datetime'
    data = el[0].firstChild.data

    # Tracker emits datetime strings in UTC or GMT.
    # The [:-4] strips the timezone indicator
    when = time.strptime(data[:-4], '%Y/%m/%d %H:%M:%S')
    # calendar.timegm treats the tuple as GMT
    return calendar.timegm(when)

  # Immutable fields
  def GetStoryId(self):
    return self.story_id

  def GetIteration(self):
    return self.iteration_number

  def GetUrl(self):
    return self.url

  # Mutable fields
  def GetRequestedBy(self):
    return self.requested_by

  def SetRequestedBy(self, requested_by):
    self.requested_by = requested_by

  def GetOwnedBy(self):
    return self.owned_by

  def SetOwnedBy(self, owned_by):
    self.owned_by = owned_by

  def GetStoryType(self):
    return self.story_type

  def SetStoryType(self, story_type):
    assert story_type in ['bug', 'chore', 'release', 'feature']
    self.story_type = story_type

  def GetCurrentState(self):
    return self.current_state

  def SetCurrentState(self, current_state):
    self.current_state = current_state

  def GetName(self):
    return self.name

  def SetName(self, name):
    self.name = name

  def GetEstimate(self):
    return self.estimate

  def SetEstimate(self, estimate):
    self.estimate = estimate

  def GetDescription(self):
    return self.description

  def SetDescription(self, description):
    self.description = description

  def GetDeadline(self):
    return self.deadline

  def SetDeadline(self, secs_since_epoch):
    self.deadline = secs_since_epoch

  def GetCreatedAt(self):
    return self.created_at

  def SetCreatedAt(self, secs_since_epoch):
    self.created_at = secs_since_epoch

  def AddLabel(self, label):
    """Adds a label (see caveat in class comment)."""
    if self.labels is None:
      self.labels = set()
    self.labels.add(label)

  def RemoveLabel(self, label):
    """Removes a label (see caveat in class comment)."""
    if self.labels is None:
      self.labels = set()
    else:
      try:
        self.labels.remove(label)
      except KeyError:
        pass

  def AddLabelsFromString(self, labels):
    """Adds a set of labels from a comma-delimited string (see class caveat)."""
    if self.labels is None:
      self.labels = set()

    self.labels = self.labels.union([x.strip() for x in labels.split(',')])

  def GetLabelsAsString(self):
    """Returns the labels as a comma delimited list of strings."""
    if self.labels is None:
      return None
    lst = list(self.labels)
    lst.sort()
    return ','.join(lst)

  def ToXml(self):
    """Converts this Story to an XML string."""
    doc = xml.dom.getDOMImplementation().createDocument(None, 'story', None)
    story = doc.getElementsByTagName('story')[0]

    # Most fields are just simple strings or ints, so we treat them all in the
    # same way.
    for field_name in self.UPDATE_FIELDS:
      v = getattr(self, field_name)
      if v is not None:
        new_tag = doc.createElement(field_name)
        new_tag.appendChild(doc.createTextNode(unicode(v)))
        story.appendChild(new_tag)

    # Labels are represented internally as sets.
    if self.labels:
      labels_tag = doc.createElement('labels')
      labels_tag.appendChild(doc.createTextNode(self.GetLabelsAsString()))
      story.appendChild(labels_tag)

    # Dates are special
    DATE_FORMAT = '%Y/%m/%d %H:%M:%S UTC'

    if self.deadline:
      formatted = time.strftime(DATE_FORMAT, time.gmtime(self.deadline))
      deadline_tag = doc.createElement('deadline')
      deadline_tag.setAttribute('type', 'datetime')
      deadline_tag.appendChild(doc.createTextNode(formatted))
      story.appendChild(deadline_tag)

    if self.created_at:
      formatted = time.strftime(DATE_FORMAT, time.gmtime(self.created_at))
      created_at_tag = doc.createElement('created_at')
      created_at_tag.setAttribute('type', 'datetime')
      created_at_tag.appendChild(doc.createTextNode(formatted))
      story.appendChild(created_at_tag)

    return doc.toxml('utf-8')
