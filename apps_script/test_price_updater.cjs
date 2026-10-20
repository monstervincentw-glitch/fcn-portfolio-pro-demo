// Isolated in-memory Apps Script services: NO Google API, credentials or network.
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const finalSource=fs.readFileSync(__dirname+'/FCN_price_updater.gs','utf8');
const originalSource=fs.readFileSync(__dirname+'/FCN_price_updater.original.gs','utf8');
let passed=0;
function test(name,fn){fn();passed++;}
function plain(x){return JSON.parse(JSON.stringify(x));}
function environment(source=finalSource){
  const e={now:Date.parse('2026-10-19T20:10:00Z'),waiting:new Set(),writes:[],copies:0,
    triggers:[{getHandlerFunction:()=> 'FCN_hourlyJob',minutes:60}],props:{},locked:false,
    denied:false,failReadback:false,reads:0,sourceDay:'2026-10-19'};
  const RealDate=Date;
  class Clock extends RealDate{constructor(...a){super(...(a.length?a:[e.now]));}static now(){return e.now;}}
  const Utilities={formatDate(d,tz,pattern){
    const p=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:tz,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(d).filter(x=>x.type!=='literal').map(x=>[x.type,x.value]));
    return `${p.year}-${p.month}-${p.day}`+(pattern.includes('HH')?` ${p.hour}`:'')+(pattern.includes('mm')?`:${p.minute}`:'')+(pattern.includes('ss')?`:${p.second}`:'');
  }};
  class Sheet{
    constructor(name,rows=1000,cols=80){this.name=name;this.rows=rows;this.cols=cols;this.cells=new Map();this.formulas=new Map();}
    getMaxRows(){return this.rows;} getMaxColumns(){return this.cols;}
    insertRowsAfter(n,qty){this.rows+=qty;}insertColumnsAfter(n,qty){this.cols+=qty;}
    getLastRow(){return Math.max(0,...[...this.cells.keys()].filter(k=>this.cells.get(k)!=='').map(k=>+k.split(',')[0]));}
    getLastColumn(){return Math.max(0,...[...this.cells.keys()].filter(k=>this.cells.get(k)!=='').map(k=>+k.split(',')[1]));}
    setColumnWidth(){} getRange(r,c,n=1,m=1){
      if(typeof r==='string'){
        const match=r.match(/^([A-Z]+)(\d+):([A-Z]+)(\d+)$/);
        const ix=s=>[...s].reduce((a,b)=>a*26+b.charCodeAt(0)-64,0);
        c=ix(match[1]);n=+match[4]-+match[2]+1;m=ix(match[3])-c+1;r=+match[2];
      }
      const sheet=this;
      if(r+n-1>sheet.rows||c+m-1>sheet.cols)throw Error('Grid bounds');
      const range={
        getValues(){e.reads++;if(e.failReadback&&sheet.name==='收盤價矩陣'&&e.writes.length){e.failReadback=false;throw Error('Injected post-write crash');}
          return Array.from({length:n},(_,i)=>Array.from({length:m},(_,j)=>sheet.cells.get(`${r+i},${c+j}`)??''));},
        getValue(){return this.getValues()[0][0];},
        getFormulas(){return Array.from({length:n},(_,i)=>Array.from({length:m},(_,j)=>sheet.formulas.get(`${r+i},${c+j}`)||''));},
        setValues(values){for(let i=0;i<n;i++)for(let j=0;j<m;j++){
          if(sheet.name==='收盤價矩陣')e.writes.push({row:r+i,col:c+j,old:sheet.cells.get(`${r+i},${c+j}`)??'',value:values[i][j]});
          sheet.cells.set(`${r+i},${c+j}`,values[i][j]);
        }return this;},
        setValue(v){return this.setValues([[v]]);},
        setFormulas(values){for(let i=0;i<n;i++)for(let j=0;j<m;j++)if(values[i][j]){
          const row=r+i,col=c+j,formula=values[i][j];sheet.formulas.set(`${row},${col}`,formula);
          sheet.cells.set(`${row},${col}`,'Date');sheet.cells.set(`${row},${col+1}`,'Close');
        }return this;},
        clearContent(){throw Error('Unexpected staging clear');},
        setBackground(){return this;},setFontWeight(){return this;},
        copyTo(dest){
          e.copies++;
          const values=this.getValues();
          // Simulate a settled historical array or an unresolved formula.
          for(let j=0;j<m;j+=2){
            const symbol=values[0][j];
            if(!e.waiting.has(symbol)){values[2][j]=e.sourceDay;values[2][j+1]=100+j;}
          }
          dest.setValues(values);
        }
      };return range;
    }
  }
  const names=['收盤價矩陣','FCN_每日股價暫存','FCN_行情值快照','FCN_同步狀態','更新紀錄'];
  e.sheets=Object.fromEntries(names.map(n=>[n,new Sheet(n,1000,n==='收盤價矩陣'?530:80)]));
  e.tickers=['AAPL','NVDA',...Array.from({length:524},(_,i)=>'S'+String(i).padStart(3,'0'))];
  e.sheets['收盤價矩陣'].getRange(1,1,1,527).setValues([['交易日期',...e.tickers]]);
  e.sheets['收盤價矩陣'].getRange(2,1,1,527).setValues([['2026-10-16',...e.tickers.map(()=>90)]]);
  e.writes=[];
  const terms=new Sheet('terms',150,24),legs=new Sheet('legs',501,13);
  terms.getRange(1,1,4,2).setValues([['product_id','final_eval_date'],['ACTIVE','2026-11-01'],['EXPIRED','2026-10-16'],['UNKNOWN','']]);
  legs.getRange(1,1,4,2).setValues([['product_id','ticker'],['ACTIVE','NVDA'],['EXPIRED','AAPL'],['UNKNOWN','S020']]);
  const book={getId:()=> '1ef0Whr7-bgj37DdOnC7ug8Dyv5Ab92-AMw5n9V18UJY',
    getSheetByName:n=>e.sheets[n],insertSheet:n=>(e.sheets[n]=new Sheet(n))};
  const props={getProperty:k=>e.props[k]||null,setProperty(k,v){e.props[k]=v;},
    deleteProperty(k){delete e.props[k];}};
  const ScriptApp={getProjectTriggers:()=>e.triggers,
    deleteTrigger(t){e.triggers=e.triggers.filter(x=>x!==t);},
    newTrigger(handler){return {timeBased(){return this;},everyMinutes(n){this.n=n;return this;},
      everyHours(n){this.n=n*60;return this;},create(){const t={getHandlerFunction:()=>handler,minutes:this.n};e.triggers.push(t);return t;}};}};
  const SpreadsheetApp={CopyPasteType:{PASTE_VALUES:'values'},flush(){},
    openById(id){if(id==='1ef0Whr7-bgj37DdOnC7ug8Dyv5Ab92-AMw5n9V18UJY')return book;
      if(id==='1peKhu1Nt8UuCiCnajGqC9bT_GXyL3qCzQBO3z-VzzOI'){if(e.denied)throw Error('Central denied');
        return {getSheetByName:n=>n==='API_商品條款_V1'?terms:legs};}
      throw Error('Unexpected workbook access');},
    getActive:()=>({toast(){}})};
  const LockService={getScriptLock:()=>({tryLock(){if(e.locked)return false;e.locked=true;return true;},releaseLock(){e.locked=false;}})};
  e.context=vm.createContext({Date:Clock,Utilities,SpreadsheetApp,ScriptApp,PropertiesService:{getScriptProperties:()=>props},LockService});
  vm.runInContext(source,e.context);e.run=code=>vm.runInContext(code,e.context);
  e.context.matrix=e.sheets['收盤價矩陣'];e.context.stage=e.sheets['FCN_每日股價暫存'];
  e.tick=()=>e.run('FCN_hourlyJob()');e.state=()=>JSON.parse(e.props.FCN_STOCK_FAST_V11||'null');
  return e;
}
test('noncontiguous priority columns regression fails original',()=>{
  const e=environment(originalSource);
  e.run(`FCN_mergeIntoMatrix_(matrix,['AAPL','NVDA','S000'],new Map([['2026-10-19',new Map([['S000',30],['AAPL',10],['NVDA',20]])]]),['S000','AAPL','NVDA'])`);
  assert.notEqual(e.sheets['收盤價矩陣'].getRange(3,2).getValue(),10);
});
test('priority columns map to exact original headers; rerun idempotent',()=>{
  const e=environment();const code=`FCN_mergeIntoMatrix_(matrix,['AAPL','NVDA','S000'],new Map([['2026-10-19',new Map([['S000',30],['AAPL',10],['NVDA',20]])]]),['S000','AAPL','NVDA'])`;
  e.run(code);assert.deepEqual(e.sheets['收盤價矩陣'].getRange(3,2,1,3).getValues(),[[10,20,30]]);
  const count=e.writes.length;e.run(code);assert.equal(e.writes.length,count);
});
test('unready block retained, next block proceeds, automatic later retry',()=>{
  const e=environment();e.run('FCN_install()');
  const initial=e.state().slots[e.state().order[0]],before=JSON.stringify([...e.context.stage.formulas]);
  initial.symbols.forEach(t=>e.waiting.add(t));
  e.now+=300000;e.tick();assert.equal(e.state().pos,1);
  for(const [k,v] of JSON.parse(before))assert.equal(e.context.stage.formulas.get(k),v);
  e.waiting.clear();
  for(let i=0;i<e.state().slots.length;i++){e.now+=300000;e.tick();}
  assert.equal(e.sheets['收盤價矩陣'].getRange(3,2+e.tickers.indexOf(initial.symbols[0])).getValue(),100);
});
test('526 settled symbols pipeline finishes in 70 minutes, no historical overwrite',()=>{
  const e=environment();e.run('FCN_install()');
  const start=e.now;for(let i=0;i<14;i++){e.now+=300000;e.tick();}
  assert.equal(e.state().done,true);assert.equal((e.now-start)/60000,70);
  assert.equal(e.sheets['收盤價矩陣'].getRange(3,2,1,526).getValues()[0].filter(x=>typeof x==='number').length,526);
  assert.ok(e.writes.every(w=>w.old===''));assert.ok(e.writes.every(w=>w.row===3));
});
test('one trigger at 5 minutes; reinstall keeps state',()=>{
  const e=environment();e.run('FCN_install()');const slots=e.state().slots;
  e.run('FCN_install()');assert.equal(e.triggers.length,1);assert.equal(e.triggers[0].minutes,5);
  assert.deepEqual(e.state().slots,slots);
});
test('other trigger blocks install before removal',()=>{
  const e=environment();e.triggers.push({getHandlerFunction:()=> 'OTHER'});
  assert.throws(()=>e.run('FCN_install()'),/Other trigger/);assert.equal(e.triggers.length,2);
});
test('missing central permission keeps original hourly trigger',()=>{
  const e=environment();e.denied=true;assert.throws(()=>e.run('FCN_install()'),/denied/);
  assert.equal(e.triggers[0].minutes,60);
});
test('lock prevents any I/O',()=>{
  const e=environment();e.locked=true;const reads=e.reads;e.tick();assert.equal(e.reads,reads);assert.equal(e.writes.length,0);
});
test('deadline retains checkpoint and pending source',()=>{
  const e=environment();e.run('FCN_install()');const before=e.props.FCN_STOCK_FAST_V11;
  assert.throws(()=>e.run('FCN_hourlyJobUnlocked_(1)'),/budget/);assert.equal(e.props.FCN_STOCK_FAST_V11,before);assert.equal(e.writes.length,0);
});
test('write/readback failure resumes without rewriting successful cells',()=>{
  const e=environment();e.run('FCN_install()');const before=e.props.FCN_STOCK_FAST_V11;e.failReadback=true;
  assert.throws(()=>e.tick(),/post-write/);assert.equal(e.props.FCN_STOCK_FAST_V11,before);
  e.tick();assert.equal(e.state().pos,1);assert.ok(e.writes.every(w=>w.old===''));
});
test('legacy pending block and cursor preserved on install',()=>{
  const e=environment();e.props.FCN_STOCK_STAGE_ACTIVE=JSON.stringify({symbols:['AAPL']});e.props.FCN_STOCK_BATCH_CURSOR='40';
  e.run(`FCN_writeNextStage_(stage,['AAPL'],27,1)`);const f=e.context.stage.formulas.get('2,1');
  e.run('FCN_install()');assert.equal(e.context.stage.formulas.get('2,1'),f);assert.equal(e.props.FCN_STOCK_BATCH_CURSOR,'40');
});
test('invalid rows and duplicate dates fail closed',()=>{
  const e=environment();e.context.matrix.getRange(4,1).setValue('2026-10-19');
  assert.throws(()=>e.run('FCN_matrixDates_(matrix)'),/空白/);
  e.context.matrix.getRange(3,1).setValue('2026-10-16');assert.throws(()=>e.run('FCN_matrixDates_(matrix)'),/遞增/);
});
test('strict price/date parser rejects bool strings nonfinite weekends future',()=>{
  const e=environment();e.context.grid=[['AAPL',''],['Date','Close'],
    ['2026-10-16',101],['2026-10-17',200],['2026-10-19',true],['2026-10-19','200'],['2026-10-20',200],
    ['2026-02-30',10],['2026-10-19',Infinity]];
  const out=e.run(`FCN_parseStage_(grid,['AAPL'],'2026-10-19')`);
  assert.equal(out.byDay.size,1);assert.equal(out.byDay.get('2026-10-16').get('AAPL'),101);
});
test('NYSE dates, DST, early close, New Year Saturday exception',()=>{
  const e=environment();
  for(const [instant,day] of [['2026-10-19T19:59:00Z','2026-10-16'],['2026-10-19T20:05:00Z','2026-10-19'],
    ['2026-11-02T21:05:00Z','2026-11-02'],['2026-11-27T18:05:00Z','2026-11-27'],
    ['2026-11-26T22:00:00Z','2026-11-25'],['2027-12-31T22:00:00Z','2027-12-31']]){
    assert.equal(e.run(`FCN_expectedDay_(new Date('${instant}'))`),day);
  }
});
test('priority uses current dated central legs, not stale close or KO cache',()=>{
  const e=environment();const p=e.run(`FCN_priority_('2026-10-19')`);
  assert.equal(p.has('NVDA'),true);assert.equal(p.has('S020'),true);assert.equal(p.has('AAPL'),false);
  e.run('FCN_install()');assert.deepEqual(e.state().slots[0].symbols.slice(0,2),['NVDA','S020']);
});
test('known holiday and gap never create an incorrect row',()=>{
  const e=environment();
  assert.equal(e.run(`FCN_hasGap_('2026-10-16','2026-10-19')`),false);
  assert.equal(e.run(`FCN_hasGap_('2026-10-16','2026-10-20')`),true);
  assert.equal(e.run(`FCN_tradingDay_('2026-12-25')`),false);
});
test('preexisting nonblank invalid values are not overwritten',()=>{
  const e=environment();e.context.matrix.getRange(3,1,1,3).setValues([['2026-10-19',0,'#N/A']]);e.writes=[];
  e.run(`FCN_mergeIntoMatrix_(matrix,['AAPL','NVDA'],new Map([['2026-10-19',new Map([['AAPL',10],['NVDA',20]])]]),['NVDA','AAPL'])`);
  assert.equal(e.writes.length,0);
});
test('missing quotes get three passes, remain blank, pending formulas survive',()=>{
  const e=environment();e.waiting.add('NVDA');e.run('FCN_install()');
  const first=e.context.stage.formulas.get('2,1');
  for(let i=0;i<42;i++){e.now+=300000;e.tick();}
  assert.equal(e.state().done,true);assert.equal(e.state().pass,3);assert.equal(e.state().missing,1);
  assert.equal(e.context.stage.formulas.get('2,1'),first);
  assert.equal(e.context.matrix.getRange(3,3).getValue(),'');
  const reads=e.reads;e.tick();assert.equal(e.reads,reads);
  e.now=Date.parse('2026-10-20T20:10:00Z');e.tick();
  assert.equal(e.state().day,'2026-10-20');assert.equal(e.state().done,false);
});
test('source quotes with an intervening missing trading day do not claim stored completion',()=>{
  const e=environment();e.now=Date.parse('2026-10-20T20:10:00Z');e.sourceDay='2026-10-20';
  e.run('FCN_install()');for(let i=0;i<14;i++){e.now+=300000;e.tick();}
  assert.equal(e.context.matrix.getLastRow(),2);assert.equal(e.state().pass,2);assert.equal(e.state().done,false);
});
test('mismatched formula cannot put another symbol price under a valid header',()=>{
  const e=environment();e.run(`FCN_writeNextStage_(stage,['AAPL'],27)`);
  e.context.stage.formulas.set('2,1','=GOOGLEFINANCE("NVDA","close",TODAY()-27,TODAY(),"DAILY")');
  assert.throws(()=>e.run(`FCN_writeNextStage_(stage,['AAPL'],27)`),/mismatch/);
});
console.log(`PASS: ${passed} isolated updater tests; no Google calls. Throughput model: 526/40, 14 five-minute intervals = 70 minutes; not a live SLA.`);
