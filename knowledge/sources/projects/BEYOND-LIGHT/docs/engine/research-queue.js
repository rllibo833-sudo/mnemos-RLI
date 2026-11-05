(() => {
"use strict";
const KEY="beyond-light.research-review-queue.v1";
const read=()=>{try{const value=JSON.parse(localStorage.getItem(KEY)||"[]");return Array.isArray(value)?value:[];}catch(_){return [];}};
const write=items=>localStorage.setItem(KEY,JSON.stringify(items.slice(0,200)));
function list(){return read();}
function add(candidate,pathway){
 const items=read(),candidateId=String(candidate.id||"candidate"),existing=items.find(x=>x.candidateId===candidateId);
 if(existing)return existing;
 const item={id:"review-"+Date.now()+"-"+items.length,candidateId,title:String(candidate.sourceTitle||"")+" ↔ "+String(candidate.targetTitle||""),question:String(pathway.question||""),status:"REVIEW_REQUIRED",createdAt:new Date().toISOString(),updatedAt:new Date().toISOString(),reviewNote:"",lastOutcome:null};
 items.unshift(item);write(items);return item;
}
function update(id,patch){
 const items=read(),index=items.findIndex(x=>x.id===id);if(index<0)throw new Error("Queue item not found.");
 const statuses=["REVIEW_REQUIRED","REVIEWED","TESTED","BLOCKED"];
 if(patch.status&&!statuses.includes(patch.status))throw new Error("Invalid review status.");
 items[index]={...items[index],status:patch.status||items[index].status,reviewNote:String(patch.reviewNote??items[index].reviewNote).slice(0,1000),lastOutcome:patch.lastOutcome??items[index].lastOutcome,updatedAt:new Date().toISOString()};
 write(items);return items[index];
}
function remove(id){write(read().filter(x=>x.id!==id));}
window.BeyondLightResearchQueue={list,add,update,remove};
})();