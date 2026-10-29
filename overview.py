"""Current-week class occurrences and recording coverage in the timetable timezone."""
from datetime import datetime, date, timedelta, time
from zoneinfo import ZoneInfo


def weekly_overview(recordings, config, now=None):
    zone=ZoneInfo(config['timezone'])
    now=(now or datetime.now(zone)).astimezone(zone)
    result={'now':now.isoformat(),'week':None,'classes':[],'past_count':0,'matched_count':0,
            'uploaded_count':0,'coverage_percent':None,'current':None,'next':None}
    if not config['week_one']:
        return result
    first=date.fromisoformat(config['week_one'])
    week=(now.date()-first).days//7+1
    if not 1<=week<=config['semester_weeks']:
        result['season']='upcoming' if week<1 else 'ended'
        return result
    start=first+timedelta(days=(week-1)*7)
    result.update(week=week,start=start.isoformat(),end=(start+timedelta(days=6)).isoformat())
    total_seconds=captured_seconds=0
    for index,slot in enumerate(config['lectures']):
        day=start+timedelta(days=(slot['day']-start.weekday())%7)
        lower=datetime.combine(day,time.fromisoformat(slot['start']),zone)
        upper=datetime.combine(day,time.fromisoformat(slot['end']),zone)
        status='past' if upper<=now else 'current' if lower<=now else 'upcoming'
        matches=[];intervals=[]
        for recording in recordings:
            route=recording.get('route')
            if not route or recording['status']=='ignored' or route['course']!=slot['course'] or route['week']!=week or not recording.get('recorded_at'):
                continue
            at=datetime.fromisoformat(recording['recorded_at']).astimezone(zone)
            if at.date()!=day or not lower-timedelta(minutes=config['tolerance_minutes'])<=at<upper:
                continue
            exact=any(s['course']==slot['course'] and s['day']==at.weekday() and s['start']<=at.strftime('%H:%M')<s['end'] for s in config['lectures'])
            if at<lower and exact:
                continue
            finish=at+timedelta(seconds=recording.get('duration') or 0)
            a,b=max(at,lower),min(finish,upper)
            matches.append(recording['id'])
            if a<b:intervals.append((a.timestamp(),b.timestamp()))
        merged=[]
        for a,b in sorted(intervals):
            if merged and a<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],b)
            else:merged.append([a,b])
        captured=sum(b-a for a,b in merged)
        item={**slot,'index':index,'date':day.isoformat(),'starts_at':lower.isoformat(),'ends_at':upper.isoformat(),
              'status':status,'recording_ids':matches,'recorded_minutes':round(captured/60),
              'coverage_percent':round(100*captured/(upper-lower).total_seconds())}
        result['classes'].append(item)
        if status=='past':
            result['past_count']+=1
            result['matched_count']+=bool(matches)
            result['uploaded_count']+=any(r['id'] in matches and r['status']=='uploaded' for r in recordings)
            total_seconds+=(upper-lower).total_seconds();captured_seconds+=captured
        elif status=='current':result['current']=item
    result['classes'].sort(key=lambda c:c['starts_at'])
    result['next']=next((c for c in result['classes'] if c['status']=='upcoming'),None)
    if total_seconds:result['coverage_percent']=round(100*captured_seconds/total_seconds)
    return result
