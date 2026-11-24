"""Deterministic director fixtures. No provider or network calls."""
from copy import deepcopy


def actor(cid,name,voice="female",shirt="#397C85",hair="long"):
    return {"id":cid,"name":name,"voice_type":voice,"appearance":{"skin_color":"#CAA087","hair_color":"#172638","shirt_color":shirt,"pants_color":"#2A4F68","shoe_color":"#1D3041","hair_style":hair,"clothing":"kameez" if hair=="long" else "shirt","eye_color":"#594035","face_shape":"oval"}}


def action(cid,kind,start,end,**kw):
    return {"character_id":cid,"type":kind,"start":start,"end":end,**kw}


def scene(duration,environment,ids,actions,**kw):
    return {"duration":duration,"environment":environment,"character_ids":ids,"actions":actions,"lighting":"day",
            "actors":[{"character_id":cid,"x":(i+1)/(len(ids)+1),"y":.82,"pose":"stand"} for i,cid in enumerate(ids)],
            "camera":[{"time":0,"shot":"wide","focus_id":ids[0]},{"time":duration,"shot":"medium","focus_id":ids[0]}],
            "props":[],"speech":[],"sounds":[],"transition":"dissolve",**kw}


def meera_with_invalid_prop_support():
    """A plausible planner response for the 30-second Dadi Ka Sandook report."""
    meera = "meera"
    box = {"id": "box", "type": "box", "x": .62, "y": .68, "support_id": "table"}
    pendant = {"id": "pendant", "type": "pendant", "x": .62, "y": .68, "support_id": "box"}
    lamp = {"id": "lamp", "type": "lamp", "x": .84, "y": .82}
    return {
        "schema_version": 3,
        "title": "Dadi Ka Sandook",
        "mood": "gentle",
        "characters": [actor(meera, "Meera")],
        "scenes": [
            scene(10, "home", [meera], [action(meera, "reach", 1, 3, target_id="box")],
                  lighting="warm", props=[dict(box), dict(lamp)]),
            scene(10, "home", [meera], [action(meera, "pick_up", 2, 4, target_id="pendant"),
                                       action(meera, "react", 4, 6, expression="happy")],
                  lighting="warm", props=[dict(box), pendant, dict(lamp)],
                  speech=[{"track": "dialogue", "speaker_id": meera,
                           "text": "Aap kehti thi, jab darr lage toh chaand ko dekh lena.", "start": 4}]),
            scene(10, "home", [meera], [action(meera, "look", 1, 3),
                                       action(meera, "react", 4, 7, expression="happy")],
                  lighting="warm", props=[dict(box), dict(lamp)]),
        ],
    }


def fixtures():
    j="jannat"
    room=[{"id":"bed","type":"bed","x":.38,"y":.83},{"id":"door","type":"door","x":.86,"y":.83},{"id":"lamp","type":"lamp","x":.1,"y":.78}]
    a={"schema_version":3,"title":"Jannat — Midnight","mood":"suspense","characters":[actor(j,"جنت")],"scenes":[
        scene(7,"bedroom",[j],[action(j,"sleep",0,2),action(j,"wake",2,3.5),action(j,"react",2.3,3,expression="scared")],
              lighting="night",props=room,actors=[{"character_id":j,"x":.45,"y":.82,"pose":"sleep"}],
              speech=[{"track":"narration","speaker_id":"narrator","text":"آدھی رات کو، جنت ایک بار پھر اسی خواب سے جاگ اٹھی۔","start":.4}]),
        scene(8,"bedroom",[j],[action(j,"react",0,1,expression="scared"),action(j,"look",5.8,7,value=1)],
              lighting="night",props=room,actors=[{"character_id":j,"x":.45,"y":.82,"pose":"sit"}],
              camera=[{"time":0,"shot":"close","focus_id":j},{"time":8,"shot":"close","focus_id":j}],
              speech=[{"track":"dialogue","speaker_id":j,"text":"یہ خواب... اتنا حقیقی کیوں لگ رہا تھا؟","start":.5}]),
        scene(5,"home",[j],[action(j,"react",0,1,expression="sad"),action(j,"pick_up",1,3,target_id="pendant")],
              lighting="memory",props=[{"id":"table","type":"table","x":.61,"y":.82},{"id":"pendant","type":"pendant","x":.61,"y":.82,"support_id":"table"}],
              camera=[{"time":0,"shot":"medium","focus_id":j},{"time":5,"shot":"close","focus_id":j}]),
        scene(10,"bedroom",[j],[action(j,"stand",0,1.5),action(j,"walk",1.5,5,to={"x":.72,"y":.83}),action(j,"look",5,6,value=1),action(j,"react",7,8,expression="scared")],
              lighting="night",props=room,actors=[{"character_id":j,"x":.45,"y":.82,"pose":"sit"}],sounds=[{"type":"door_click","at":7.2}],
              camera=[{"time":0,"shot":"wide","focus_id":j},{"time":6,"shot":"medium","focus_id":j},{"time":10,"shot":"medium","focus_id":j}])
    ]}
    fox=actor("nora","Nora","female","#D59A58","curly")
    fox["appearance"].update(skin_color="#CB895A",hair_color="#7F5039",eye_color="#5B4B39")
    b={"schema_version":3,"title":"Nora finds the lost ball","mood":"playful","characters":[{**fox,"species":"fox"}],"scenes":[
        scene(5,"garden",["nora"],[action("nora","run",0,2.3,to={"x":.66,"y":.82}),action("nora","pick_up",2.4,3.6,target_id="ball"),action("nora","react",3.7,4.5,expression="happy")],
              props=[{"id":"ball","type":"ball","x":.77,"y":.82,"color":"#CE6A64"}],
              speech=[{"track":"dialogue","speaker_id":"nora","text":"There it is!","start":.6}]),
        scene(5,"beach",["nora"],[action("nora","jump",0,1.5),action("nora","wave",1.5,3.5),action("nora","turn",3.5,4.8,value=-1)],
              speech=[{"track":"dialogue","speaker_id":"nora","text":"Let's play together.","start":1}])
    ]}
    c={"schema_version":3,"title":"The library surprise","mood":"gentle","characters":[actor("mira","Mira","female","#8A68A5"),actor("arun","Arun","male","#4D80A8","short")],"scenes":[
        scene(6,"school",["mira","arun"],[action("mira","walk",0,1.5,to={"x":.43,"y":.82}),action("mira","pick_up",1.6,3,target_id="book"),action("arun","look",.2,1,value=-1),action("arun","wave",3,5)],
              props=[{"id":"table","type":"table","x":.54,"y":.82},{"id":"book","type":"book","x":.54,"y":.82,"color":"#9D6659","support_id":"table"}],
              speech=[{"track":"dialogue","speaker_id":"mira","text":"Arun, yeh kitaab dekho.","start":.3},{"track":"dialogue","speaker_id":"arun","text":"Wah, kya baat hai!","start":3}]),
        scene(6,"workshop",["mira","arun"],[action("arun","walk",0,2,to={"x":.78,"y":.82}),action("arun","open_door",2,3.5,target_id="door"),action("mira","point",2,3.5,target_id="door"),action("arun","close_door",4,5.5,target_id="door")],
              props=[{"id":"door","type":"door","x":.85,"y":.82},{"id":"table","type":"table","x":.15,"y":.83}])
    ]}
    return deepcopy({"jannat":a,"garden":b,"library":c})
