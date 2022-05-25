import requests
import json

f = open('FBI.html','w')

for num in range(1,10):
    response = requests.get('https://api.fbi.gov/wanted/v1/list', params={
        'page': num
    })
    data = json.loads(response.content)
    for x in data['items']:
        if (x['caution'] != None):
            f.write('<p>' + str(x['path']) + '</p>')
            if (x['subjects'] != []):
                f.write('<p>' + str(x['subjects']) + '</p>')
            caution = str(x['caution'])
            f.write(caution.replace('<p> </p>', ''))
            f.write('<p> </p>')


f.close()
