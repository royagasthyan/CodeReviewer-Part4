import argparse
import json
import os
import re
import random
import time
import smtplib
import imaplib
import uuid
import email
import datetime
from datetime import timedelta
import logging
from logging.handlers import RotatingFileHandler
from copy import copy

#
# Global variables
#
project_url = ''
project_members = ''
followup_frequency = ''
no_days = ''
project = ''

FROM_EMAIL      = "your_email_address@gmail.com"
FROM_PWD        = "your_password"
SERVER     = "smtp.gmail.com"
PORT       = 587

# ----------------------------------
#
# Utility to execute system commands
#
# ----------------------------------

def execute_cmd(cmd):
    print "***** Executing command '"+ cmd + "'"
    response = os.popen(cmd).read()
    return response

# -------------------------------------------
#
# Commit class to contain commit related info
#
# -------------------------------------------

class Commit:
    def __init__(self, Id, Author, Date):
        self.Id = Id;
        self.Author = Author;
        self.Date = Date;

# ----------------------------------
#
# Process the git log 
#
# ----------------------------------

def process_commits():
    cmd = "cd " + project + "; git log --all --since=" + str(no_days) + ".day --name-status"
    response = execute_cmd(cmd)
    commitId = ''
    author = ''
    date = ''
    commits = []

    for line in response.splitlines():
        if line.startswith('commit '):
            if commitId <> "":
                commits.append(Commit(commitId, author, date))
            author = ''
            date = ''
            commitId = line[7:]
        if line.startswith('Author:'):
            if(re.search('\<(.*?)\>',line)):
                author = re.search('\<(.*?)\>',line).group(1)
        if line.startswith('Date:'):
            date = line[5:]

    if commitId <> "":
        commits.append(Commit(commitId, author, date))

    return commits

# ------------------------------------------
#
# Method to Schedule the code review request
#
# ------------------------------------------

def schedule_review_request(commits):
    date = time.strftime("%Y-%m-%d")
    
    for commit in commits:
        reviewer = select_reviewer(commit.Author, project_members)
        subject = date + " Code Review [commit:" + commit.Id + "]"
        body = "Hello '" + reviewer + "', you have been selected to review the code for commit\n"
        body += "done by '" + commit.Author + "'.\n"
        body += "\n"
        
        body += format_review_commit(commit)

        save_review_info(reviewer,subject);

        send_email(reviewer,subject,body)

# -----------------------------------------
#
# Method to select random reviewer
#
# -----------------------------------------

def select_reviewer(author, group):
    if author in group:
        group.remove(author)
    reviewer = random.choice(group)
    return reviewer

# -----------------------------------------
#
# Utility to format review request
#
# -----------------------------------------

def format_review_commit(commit):
    review_req = ""
    review_req += "URL:     " + project_url + '/commit/' +  commit.Id + "\n"
    review_req += "Commit:  " + commit.Id + "\n"
    review_req += "Author:  " + commit.Author + "\n"
    review_req += "Date:    " + commit.Date + "\n"
    return review_req

# -----------------------------------------
#
# Utility to send email
#
# -----------------------------------------

def send_email(to, subject, body):
    header  = "From: " + FROM_EMAIL + "\n"
    header += "To: " + to + "\n"
    header += "Subject: " + subject + "\n"
    header += "\n"
    header += body

    print "** Sending email to '" + to + "'"
    
    
    mail_server = smtplib.SMTP(SERVER, PORT)
    mail_server.starttls()
    mail_server.login(FROM_EMAIL, FROM_PWD)
    mail_server.sendmail(FROM_EMAIL, to, header)
    mail_server.quit()

# ----------------------------------------
#
# Utility to save code review request info
#
# ----------------------------------------
def save_review_info(reviewer, subject):
    info = {'reviewer':reviewer,'subject':subject,'id':str(uuid.uuid4()),'sendDate':str(datetime.date.today())}

    with open('reviewer.json','r') as infile:
        review_data = json.load(infile)

    review_data.append(info)

    with open('reviewer.json','w') as outfile:
        json.dump(review_data,outfile)

# -------------------------------------------
#
# Utility to read email inbox
#
# -------------------------------------------
def read_email(num_days):
    try:
        email_info = []
        email_server = imaplib.IMAP4_SSL(SERVER)
        email_server.login(FROM_EMAIL,FROM_PWD)
        email_server.select('inbox')

        email_date = datetime.date.today() - timedelta(days=num_days)
        formatted_date = email_date.strftime('%d-%b-%Y')

        typ, data = email_server.search(None, '(SINCE "' + formatted_date + '")')
        ids = data[0]

        id_list = ids.split()

        first_email_id = int(id_list[0])
        last_email_id = int(id_list[-1])

        for i in range(last_email_id,first_email_id, -1):
            typ, data = email_server.fetch(i, '(RFC822)' )

            for response_part in data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_string(response_part[1])
                    email_info.append({'From':msg['from'],'Subject':msg['subject'].replace("\r\n","")})
                    
    except Exception, e:
        logger.error(str(datetime.datetime.now()) + " - Error while reading mail : " + str(e) + "\n")
        logger.exception(str(e))

    return email_info

# -----------------------------------
#
# Follow up code review request
#
# -----------------------------------

def followup_request():
    with open('reviewer.json','r') as jfile:
        review_info = json.load(jfile)
    review_info_copy = copy(review_info)

    email_info = read_email(no_days)

    for review in review_info:
        review_date = datetime.datetime.strptime(review['sendDate'],'%Y-%m-%d')
        today = datetime.datetime.today()
        days_since_review = (today - review_date).days
        review_replied = False
        expected_subject = 'Re: ' + review['subject']
        for email in email_info:
            if expected_subject == email['Subject']:
                review_replied = True
                review_info_copy = Delete_Info(review_info_copy,review['id'])
                break;

        if not review_replied:
            if days_since_review > followup_frequency:
                send_email(review['reviewer'],'Reminder: ' + review['subject'],'\nYou have not responded to the review request\n')

    if review_info_copy != review_info:
        with open('reviewer.json','w') as outfile:
            json.dump(review_info_copy,outfile)

# -----------------------------------------
#
# Delete Info from Review Information
#
# -----------------------------------------

def Delete_Info(info, id):
    for i in xrange(len(info)):
        if info[i]['id'] == id:
            info.pop(i)
            break
    return info

#
# Read the program parameters
#
parser = argparse.ArgumentParser(description="Code Review Scheduler Program")
parser.add_argument("-n", nargs="?", type=int, default=1, help="Number of (d)ays to look for log. ")
parser.add_argument("-p", nargs="?", type=str, default="em", help="Project name.")
args = parser.parse_args()

no_days = args.n
project = args.p

logger = logging.getLogger("Code Review Scheduler Log")
logger.setLevel(logging.INFO)

logHandler = RotatingFileHandler('app.log',maxBytes=3000,backupCount=2)
logger.addHandler(logHandler)

#
# Read the scheduler config file
#
with open('config.json') as cfg_file:
    main_config = json.load(cfg_file)

for p in main_config:
    if p['name'] == project:
        project_url = p['git_url']
        project_members = p['members']
        followup_frequency = p['followup_frequency']
	break


if not os.path.exists('reviewer.json'):
    with open('reviewer.json','w+') as outfile:
        json.dump([],outfile)

# Clone the repository if not already exists
print "********* Doing project checkout **********"
if(os.path.isdir("./" + project)):
    execute_cmd("cd " + project + "; git pull")
else:
    execute_cmd("git clone " + project_url + " " + project)
print "*** Done *******"
print " "

print 'Processing the scheduler against project ' + project + '....'


try:
    commits = process_commits()

    followup_request()

    if len(commits) == 0:
        print 'No commits found '
    else:
        schedule_review_request(commits)

except Exception,e:
    print 'Error occurred. Check log for details.'
    logger.error(str(datetime.datetime.now()) + " - Error occurred : " + str(e) + "\n")
    logger.exception(str(e))
