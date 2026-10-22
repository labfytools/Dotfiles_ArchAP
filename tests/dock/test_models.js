const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
function load(file) {
    const context=vm.createContext({});
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../../quickshell/.config/quickshell/labfy-sway',file),'utf8')
        .replace(/^\.pragma library\s*\n/,''),context);
    return context;
}
const hide=load('dock/AutoHide.js');
let phase='hidden';
const input={suppressed:false,held:false,body:false,edge:false};
const event=(name='input') => phase=hide.next(phase,name,input);
assert.equal(event(),'hidden');
input.edge=true; assert.equal(event(),'arming');
input.edge=false; assert.equal(event(),'hidden');
input.edge=true; event(); assert.equal(event('deadline'),'shown');
input.edge=false; assert.equal(event(),'waiting');
input.body=true; assert.equal(event(),'shown');
input.body=false; event(); input.held=true; assert.equal(event(),'held');
assert.equal(event('deadline'),'held');
input.held=false; assert.equal(event(),'waiting');
assert.equal(event('deadline'),'hidden');
input.held=true; event(); input.suppressed=true; assert.equal(event(),'hidden');
assert.equal(hide.influence(0),1);
assert.ok(hide.influence(25)>hide.influence(55));
assert.equal(hide.influence(76),0);
assert.equal(hide.influence(-76),0);
assert.equal(hide.influence(-35),hide.influence(35));
for (let cursor=0; cursor<570; ++cursor) {
    const affected=Array.from({length:10},(_,i)=>i).filter(i=>hide.influence(i*57-cursor)>0);
    assert.ok(affected.length<=3);
    assert.ok(affected.length===0 || affected.at(-1)-affected[0]<=2);
}
const model=load('applications/WindowModel.js');
const apps=[{id:'kitty.desktop',aliases:['kitty'],iconSource:'file:///tela/kitty.svg'},
    {id:'org.app.desktop',aliases:['startup-class','executable']},
    {id:'org.other.desktop',aliases:['executable']}];
assert.equal(model.match(apps,{appId:'kitty'}).id,'kitty.desktop');
assert.equal(model.match(apps,{wmClass:'Startup-Class'}).id,'org.app.desktop');
assert.equal(model.match(apps,{appId:'executable'}),null);
assert.equal(model.match(apps,{title:'kitty'}),null);
let entries=model.entries(apps,['absent.desktop','kitty.desktop'],[{id:'10',appId:'kitty'},{id:'11',appId:'kitty'},
    {id:'12',appId:'unknown'}]);
assert.equal(entries[0].missing,true);
assert.equal(entries[1].windows.length,2);
assert.equal(entries[1].iconSource,apps[0].iconSource);
assert.equal(entries[2].pinned,false);
assert.equal(model.entries(apps,[],[]).length,0);
assert.equal(model.entries(apps,[],[{id:'11',appId:'kitty'}])[0].pinned,false);
assert.equal(model.entries(apps,['kitty.desktop'],[])[0].windows.length,0);
console.log('Dock state and window models: PASS');
