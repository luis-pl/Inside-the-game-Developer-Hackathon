SELECT match_id FROM analytics.events WHERE event_id=? AND match_id IN(SELECT TRY_CONVERT(int,value) FROM OPENJSON(?));
