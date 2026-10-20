// FCN v1.1: patch of user-supplied v1.0. Replace original file; do NOT add a second writer.
// Isolated tests only; live Apps Script/GOOGLEFINANCE must be verified by the owner.
const FCN_CONFIG = Object.freeze({
  SPREADSHEET_ID:'1ef0Whr7-bgj37DdOnC7ug8Dyv5Ab92-AMw5n9V18UJY',
  MATRIX:'收盤價矩陣',STAGING:'FCN_每日股價暫存',SNAPSHOT:'FCN_行情值快照',
  STATUS:'FCN_同步狀態',LOG:'更新紀錄',TIME_ZONE:'America/New_York',
  INTERVAL_MINUTES:5,MAX_RUN_MS:180000,MAX_PASSES:3,STATE:'FCN_STOCK_FAST_V11',
  CENTRAL_ID:'1peKhu1Nt8UuCiCnajGqC9bT_GXyL3qCzQBO3z-VzzOI',
  BATCH_SIZE:40,HISTORY_DAYS:27,STAGING_ROWS:100,MIN_READY_RATE:0.60,
  PROPS_CURSOR:'FCN_STOCK_BATCH_CURSOR',PROPS_STAGE:'FCN_STOCK_STAGE_ACTIVE',
  PROPS_LOOKBACK:'FCN_STOCK_LOOKBACK_DAYS'
});
function FCN_install(){
  const lock=LockService.getScriptLock();if(!lock.tryLock(5000))throw Error('Updater busy; retry later.');
  try{
    const ss=SpreadsheetApp.openById(FCN_CONFIG.SPREADSHEET_ID),{matrix,tickers}=FCN_getSource_(ss);
    if(tickers.length!==526||matrix.getLastRow()<2)throw Error('Expected existing 526-stock matrix.');
    FCN_matrixDates_(matrix);
    FCN_priority_(FCN_expectedDay_(new Date())); // Permission/header preflight BEFORE trigger edits.
    const ts=ScriptApp.getProjectTriggers();
    if(ts.some(t=>t.getHandlerFunction()!=='FCN_hourlyJob'))throw Error('Other trigger exists; identify writer before installing.');
    FCN_getOrCreateStage_(ss);FCN_getOrCreateSnapshot_(ss);FCN_getOrCreateStatus_(ss);
    ts.forEach(t=>ScriptApp.deleteTrigger(t));
    ScriptApp.newTrigger('FCN_hourlyJob').timeBased().everyMinutes(FCN_CONFIG.INTERVAL_MINUTES).create();
    if(ScriptApp.getProjectTriggers().filter(t=>t.getHandlerFunction()==='FCN_hourlyJob').length!==1)
      throw Error('Trigger verification failed; inspect trigger list.');
    // Keep old cursor/active staging. Never reset or clear a pending batch on install.
  }finally{lock.releaseLock();}
  FCN_hourlyJob();
}
function FCN_hourlyJob(){
  const lock=LockService.getScriptLock();if(!lock.tryLock(5000))return;
  try{FCN_hourlyJobUnlocked_(Date.now()+FCN_CONFIG.MAX_RUN_MS);}
  catch(err){
    FCN_recordError_(err.code==='FCN_BUDGET'?'本次時間上限；保留斷點，下次接續':String(err.message||err));
    if(err.code!=='FCN_BUDGET')throw err;
  }finally{lock.releaseLock();}
}
function FCN_hourlyJobUnlocked_(deadline){
  const now=new Date(),target=FCN_expectedDay_(now),props=PropertiesService.getScriptProperties();
  let state=JSON.parse(props.getProperty(FCN_CONFIG.STATE)||'null');
  if(state&&state.day===target&&state.done)return; // Weekends/pre-close: no business-data I/O.
  const ss=SpreadsheetApp.openById(FCN_CONFIG.SPREADSHEET_ID),{matrix,tickers}=FCN_getSource_(ss);
  if(tickers.length!==526)throw Error('Stock universe changed; refusing write.');
  if(!state){
    const legacy=JSON.parse(props.getProperty(FCN_CONFIG.PROPS_STAGE)||'null');
    const priority=FCN_priority_(target);
    const ordered=[...tickers.filter(t=>priority.has(t)),...tickers.filter(t=>!priority.has(t))];
    const slots=[];let remaining=ordered;
    if(legacy){
      if(!Array.isArray(legacy.symbols)||!legacy.symbols.length||legacy.symbols.length>40||
         new Set(legacy.symbols).size!==legacy.symbols.length||legacy.symbols.some(t=>!tickers.includes(t)))throw Error('Invalid legacy stage checkpoint.');
      slots.push({row:1,symbols:legacy.symbols,legacy:true});
      remaining=ordered.filter(t=>!legacy.symbols.includes(t));
    }
    for(let i=0;i<remaining.length;i+=40)slots.push({row:1+slots.length*FCN_CONFIG.STAGING_ROWS,symbols:remaining.slice(i,i+40)});
    state={slots,day:null};
  }
  if(new Set(state.slots.flatMap(x=>x.symbols)).size!==526||state.slots.flatMap(x=>x.symbols).length!==526||
     state.slots.some((x,i)=>x.row!==1+i*FCN_CONFIG.STAGING_ROWS||x.symbols.some(t=>!tickers.includes(t))))throw Error('Checkpoint/universe mismatch.');
  if(state.day!==target){
    const priority=FCN_priority_(target);
    state.order=state.slots.map((x,i)=>i).sort((a,b)=>Number(state.slots[b].symbols.some(t=>priority.has(t)))-Number(state.slots[a].symbols.some(t=>priority.has(t))));
    state.day=target;state.pos=0;state.pass=1;state.done=false;state.missing=0;
    FCN_saveState_(props,state);
  }
  const slot=state.slots[state.order[state.pos]],stage=FCN_getOrCreateStage_(ss),snapshot=FCN_getOrCreateSnapshot_(ss);
  const lookback=Number(props.getProperty(FCN_CONFIG.PROPS_LOOKBACK)||FCN_CONFIG.HISTORY_DAYS);
  FCN_guard_(deadline);
  // Each batch owns a block in the EXISTING staging/snapshot tabs. Pending blocks
  // stay intact while other batches proceed; no clearing or second price library.
  const seeded=FCN_writeNextStage_(stage,slot.symbols,lookback,slot.row,slot.legacy);
  if(seeded){FCN_writeStatus_(ss,[['同步狀態','公式準備中；下次五分鐘後讀取'],['目標交易日',target]]);return;}
  const width=slot.symbols.length*2;
  FCN_ensureRows_(snapshot,slot.row+FCN_CONFIG.STAGING_ROWS-1);
  FCN_guard_(deadline);
  stage.getRange(slot.row,1,FCN_CONFIG.STAGING_ROWS,width).copyTo(
    snapshot.getRange(slot.row,1,FCN_CONFIG.STAGING_ROWS,width),SpreadsheetApp.CopyPasteType.PASTE_VALUES,false);
  SpreadsheetApp.flush();
  const grid=snapshot.getRange(slot.row,1,FCN_CONFIG.STAGING_ROWS,width).getValues();
  const parsed=FCN_parseStage_(grid,slot.symbols,target);
  const result=FCN_mergeIntoMatrix_(matrix,tickers,parsed.byDay,slot.symbols,deadline);
  const targetRow=FCN_matrixDates_(matrix).indexOf(target)+2;
  const stored=targetRow>=2?matrix.getRange(targetRow,1,1,tickers.length+1).getValues()[0]:[];
  const missing=slot.symbols.filter(t=>{const v=stored[tickers.indexOf(t)+1];return typeof v!=='number'||!Number.isFinite(v)||v<=0;});
  state.missing+=missing.length;
  // Cursor advances only after verified writes. A partial write crash safely repeats
  // the same block; blank-only writes are idempotent. Missing data retries next pass.
  state.pos++;
  if(state.pos===state.order.length){
    state.pos=0;
    if(!state.missing||state.pass>=FCN_CONFIG.MAX_PASSES)state.done=true;
    else{state.pass++;state.missing=0;}
  }
  FCN_saveState_(props,state);
  if(result.saved){
    const log=ss.getSheetByName(FCN_CONFIG.LOG);
    if(log){const row=log.getLastRow()+1;FCN_ensureRows_(log,row);log.getRange(row,1,1,7).setValues([[
      Utilities.formatDate(now,FCN_CONFIG.TIME_ZONE,'yyyy-MM-dd HH:mm:ss'),'五分鐘接續（原FCN_hourlyJob）',
      result.firstDay+'～'+result.lastDay,slot.symbols.length,result.saved,missing.length?'部分缺價待重試':'成功','GOOGLEFINANCE → 固定值；僅填空白']]);}
  }
  FCN_writeStatus_(ss,[['最後執行時間（紐約）',Utilities.formatDate(now,FCN_CONFIG.TIME_ZONE,'yyyy-MM-dd HH:mm:ss')],
    ['排程','單一FCN_hourlyJob／每5分鐘／最多40檔'],['目標交易日',target],['本次新增價格',result.saved],
    ['輪次',state.pass],['下批位置',state.pos+1],['本批缺價',missing.join(',')||'無'],
    ['同步狀態',state.done?(state.missing?'本日重試完成；缺價保留，次日27天視窗再試':'本日全部批次有價'):'接續下一批；未完成暫存保留']]);
  if(!state.done){
    const next=state.slots[state.order[state.pos]];
    FCN_guard_(deadline);
    FCN_writeNextStage_(stage,next.symbols,lookback,next.row,next.legacy); // pipeline, no polling wait
  }
}
function FCN_parseStage_(grid,symbols,lastClosedDay){
  const byDay=new Map(),issues=[];
  symbols.forEach((ticker,i)=>{
    const col=i*2;
    if(String((grid[0]||[])[col]||'')!==ticker)throw Error('Staging header mismatch: '+ticker);
    let n=0;
    for(let r=2;r<grid.length;r++){
      const day=FCN_dateKey_(grid[r][col]),price=grid[r][col+1];
      if(!day||day>lastClosedDay||!FCN_tradingDay_(day)||typeof price!=='number'||!Number.isFinite(price)||price<=0)continue;
      if(!byDay.has(day))byDay.set(day,new Map());
      const quotes=byDay.get(day);
      if(quotes.has(ticker)&&quotes.get(ticker)!==price)throw Error('Conflicting source prices: '+ticker+' '+day);
      quotes.set(ticker,price);n++;
    }
    if(!n)issues.push(ticker+' 未取得日期化收盤價（保留暫存）');
  });return {byDay,issues};
}
function FCN_mergeIntoMatrix_(matrix,tickers,byDay,stagedSymbols,deadline){
  const existing=FCN_matrixDates_(matrix),index=new Map(existing.map((day,i)=>[day,i+2]));
  let latest=existing.at(-1)||'',saved=0;const holes=[],addedDays=[],days=[...byDay.keys()].sort();
  for(const day of days){
    FCN_guard_(deadline);const quotes=byDay.get(day);let row=index.get(day);
    if(!row){
      if(latest&&day<=latest){holes.push(day);continue;}
      if(latest&&FCN_hasGap_(latest,day)){holes.push(day);break;} // never skip missing trading days
      if(!quotes.size)continue;
      row=matrix.getLastRow()+1;FCN_ensureRows_(matrix,row);matrix.getRange(row,1).setValue(day);
      index.set(day,row);addedDays.push(day);latest=day;
    }
    const writes=[];
    for(const symbol of stagedSymbols){
      FCN_guard_(deadline);const col=tickers.indexOf(symbol)+2;if(col<2)throw Error('Unknown matrix ticker: '+symbol);
      const quote=quotes.get(symbol);if(typeof quote!=='number'||!Number.isFinite(quote)||quote<=0)continue;
      const old=matrix.getRange(row,col).getValue();
      if(old===''||old===null)writes.push({col,quote}); // Do NOT overwrite zero/error/formula/nonblank cells either.
    }
    writes.sort((a,b)=>a.col-b.col);
    for(let i=0;i<writes.length;){
      FCN_guard_(deadline);let j=i+1;while(j<writes.length&&writes[j].col===writes[j-1].col+1)j++;
      const group=writes.slice(i,j),range=matrix.getRange(row,group[0].col,1,group.length);
      const fresh=range.getValues()[0]; // recheck just before writing (same project lock)
      if(fresh.some(x=>x!==''&&x!==null))throw Error('Concurrent matrix writer detected; retry after excluding it.');
      range.setValues([group.map(x=>x.quote)]);SpreadsheetApp.flush();
      const readback=range.getValues()[0];if(group.some((x,k)=>readback[k]!==x.quote))throw Error('Write verification failed; checkpoint retained.');
      saved+=group.length;i=j;
    }
  }
  return {saved,datesAdded:addedDays.length,firstDay:days[0]||'',lastDay:days.at(-1)||'',holes};
}
function FCN_writeNextStage_(stage,symbols,lookback,startRow=1,legacy=false){
  if(!Number.isInteger(lookback)||lookback<1||lookback>90)throw Error('Invalid lookback.');
  if(!symbols.length||symbols.length>40||symbols.some(s=>!/^[A-Z0-9.^_-]{1,18}$/.test(s)))throw Error('Invalid batch.');
  const width=symbols.length*2;
  FCN_ensureRows_(stage,startRow+FCN_CONFIG.STAGING_ROWS-1);
  const grid=stage.getRange(startRow,1,FCN_CONFIG.STAGING_ROWS,width).getValues();
  const heads=symbols.every((s,i)=>grid[0][2*i]===s);
  const formulas=stage.getRange(startRow+1,1,1,width).getFormulas()[0];
  if(heads&&symbols.every((_,i)=>formulas[2*i])){
    if(symbols.some((sym,i)=>!formulas[2*i].startsWith(`=GOOGLEFINANCE("${sym}","close",`)))throw Error('Staging formula/ticker mismatch; preserve source.');
    return false;
  } // Never overwrite pending formulas/results.
  if(legacy)throw Error('Legacy stage incomplete; preserve and inspect before continuing.');
  if(grid.slice(1).some(r=>r.some(v=>v!==''&&v!==null))||formulas.some(Boolean)||
     (!heads&&grid[0].some(v=>v!==''&&v!==null)))throw Error('Reserved staging block is occupied; no clearing allowed.');
  const head=Array(width).fill(''),f=Array(width).fill('');
  symbols.forEach((sym,i)=>{head[2*i]=sym;f[2*i]=`=GOOGLEFINANCE("${sym}","close",TODAY()-${lookback},TODAY(),"DAILY")`;});
  stage.getRange(startRow,1,1,width).setValues([head]);
  stage.getRange(startRow+1,1,1,width).setFormulas([f]);SpreadsheetApp.flush();return true;
}
function FCN_getSource_(ss){
  if(ss.getId()!==FCN_CONFIG.SPREADSHEET_ID)throw Error('股價庫 ID 不一致，停止寫入。');
  const matrix=ss.getSheetByName(FCN_CONFIG.MATRIX);if(!matrix)throw Error('找不到：'+FCN_CONFIG.MATRIX);
  const header=matrix.getRange(1,1,1,matrix.getLastColumn()).getValues()[0];
  if(String(header[0]).trim()!=='交易日期')throw Error('正式矩陣 A1 不是「交易日期」，停止寫入。');
  const tickers=header.slice(1).map(x=>String(x||'').trim().toUpperCase());
  if(tickers.some(x=>!x))throw Error('正式矩陣表頭中途有空白，為避免股價寫錯欄位，停止寫入。');
  if(new Set(tickers).size!==tickers.length)throw Error('正式矩陣有重複股票欄名，停止寫入。');
  if(!tickers.length)throw Error('正式矩陣找不到股票代號');return {matrix,tickers};
}
function FCN_getOrCreateStage_(ss){
  let sh=ss.getSheetByName(FCN_CONFIG.STAGING);if(!sh)sh=ss.insertSheet(FCN_CONFIG.STAGING);
  if(sh.getMaxColumns()<FCN_CONFIG.BATCH_SIZE*2)sh.insertColumnsAfter(sh.getMaxColumns(),FCN_CONFIG.BATCH_SIZE*2-sh.getMaxColumns());
  FCN_ensureRows_(sh,FCN_CONFIG.STAGING_ROWS);return sh;
}
function FCN_getOrCreateSnapshot_(ss){
  let sh=ss.getSheetByName(FCN_CONFIG.SNAPSHOT);if(!sh)sh=ss.insertSheet(FCN_CONFIG.SNAPSHOT);
  if(sh.getMaxColumns()<FCN_CONFIG.BATCH_SIZE*2)sh.insertColumnsAfter(sh.getMaxColumns(),FCN_CONFIG.BATCH_SIZE*2-sh.getMaxColumns());
  FCN_ensureRows_(sh,FCN_CONFIG.STAGING_ROWS);return sh;
}
function FCN_getOrCreateStatus_(ss){
  let sh=ss.getSheetByName(FCN_CONFIG.STATUS);if(!sh)sh=ss.insertSheet(FCN_CONFIG.STATUS);
  sh.getRange('A1:B1').setValues([['項目','目前狀態']]);sh.getRange('A1:B1').setBackground('#EBD9BE').setFontWeight('bold');
  sh.setColumnWidth(1,230);sh.setColumnWidth(2,600);return sh;
}
function FCN_writeStatus_(ss,entries){const status=FCN_getOrCreateStatus_(ss);FCN_ensureRows_(status,entries.length+1);status.getRange(2,1,entries.length,2).setValues(entries);}
function FCN_recordError_(message){
  try{const ss=SpreadsheetApp.openById(FCN_CONFIG.SPREADSHEET_ID);FCN_writeStatus_(ss,[['最後錯誤（紐約）',Utilities.formatDate(new Date(),FCN_CONFIG.TIME_ZONE,'yyyy-MM-dd HH:mm:ss')],['錯誤內容',message]]);}catch(_){}
}
function FCN_matrixDates_(matrix){
  const last=matrix.getLastRow();if(last<2)return [];
  const rows=matrix.getRange(2,1,last-1,1).getValues(),dates=[];
  for(let i=0;i<rows.length;i++){
    const d=FCN_dateKey_(rows[i][0]);
    if(!d)throw Error('正式矩陣第'+(i+2)+'列空白或日期錯誤；停止以免寫錯列');
    if(dates.length&&d<=dates[dates.length-1])throw Error('原始日期未遞增，拒絕追加或改動');dates.push(d);
  }return dates;
}
function FCN_dateKey_(value){
  if(value instanceof Date&&!isNaN(value.getTime()))return Utilities.formatDate(value,FCN_CONFIG.TIME_ZONE,'yyyy-MM-dd');
  if(typeof value==='number'&&Number.isFinite(value)&&value>20000&&value<100000){
    const d=new Date(Date.UTC(1899,11,30)+Math.floor(value)*86400000);return Utilities.formatDate(d,'UTC','yyyy-MM-dd');
  }
  const s=String(value==null?'':value).trim().replace(/\//g,'-');
  if(/^\d{4}-\d{2}-\d{2}$/.test(s)&&!isNaN(Date.parse(s+'T00:00:00Z'))&&new Date(s+'T00:00:00Z').toISOString().slice(0,10)===s)return s;return '';
}
function FCN_ensureRows_(sheet,lastNeeded){if(sheet.getMaxRows()<lastNeeded)sheet.insertRowsAfter(sheet.getMaxRows(),Math.max(50,lastNeeded-sheet.getMaxRows()));}
function FCN_backfillLast90Days(){
  // Existing pending blocks must not be reset/replaced. Explicit separate recovery
  // needs a reviewed plan; do not silently pretend existing 27-day formulas changed.
  throw Error('加速期間保留所有未完成暫存；90天補價須先停止排程並另案處理，不更動現有公式。');
}
function FCN_stop(){
  ScriptApp.getProjectTriggers().filter(t=>t.getHandlerFunction()==='FCN_hourlyJob').forEach(t=>ScriptApp.deleteTrigger(t));
  SpreadsheetApp.getActive().toast('自動同步已停止；正式歷史價格沒有更動。','FCN 股價同步',8);
}
function onOpen(){
  SpreadsheetApp.getUi().createMenu('FCN 股價庫').addItem('啟用每日自動固定股價','FCN_install').addItem('立即執行一輪','FCN_hourlyJob').addItem('回補最近90天','FCN_backfillLast90Days').addSeparator().addItem('停止自動更新','FCN_stop').addToUi();
}

function FCN_guard_(deadline){if(deadline&&Date.now()>=deadline){const e=Error('Execution budget');e.code='FCN_BUDGET';throw e;}}
function FCN_saveState_(props,state){const raw=JSON.stringify(state);if(raw.length>8000)throw Error('Checkpoint too large; refusing truncation.');props.setProperty(FCN_CONFIG.STATE,raw);}
function FCN_priority_(day){
  const book=SpreadsheetApp.openById(FCN_CONFIG.CENTRAL_ID);
  const terms=book.getSheetByName('API_商品條款_V1').getRange('A1:X150').getValues();
  const legs=book.getSheetByName('API_標的_V1').getRange('A1:M501').getValues();
  const th=terms[0],lh=legs[0],pi=th.indexOf('product_id'),fi=th.indexOf('final_eval_date'),li=lh.indexOf('product_id'),ti=lh.indexOf('ticker');
  if([pi,fi,li,ti].some(x=>x<0))throw Error('Priority source headers changed.');
  // Conservative live-monitor superset: no stale central KO/latest_close used.
  // Unknown final dates stay included; this is ordering, never a second V2 engine.
  const ids=new Set(terms.slice(1).filter(r=>r[pi]&&(!FCN_dateKey_(r[fi])||FCN_dateKey_(r[fi])>=day)).map(r=>String(r[pi]).trim()));
  return new Set(legs.slice(1).filter(r=>ids.has(String(r[li]).trim())).map(r=>String(r[ti]||'').trim().toUpperCase()).filter(Boolean));
}
function FCN_calendarNth(year,month,dow,n){
  const first=new Date(Date.UTC(year,month-1,1));
  return 1+(dow-first.getUTCDay()+7)%7+7*(n-1);
}
function FCN_calendarLast(year,month,dow){
  const last=new Date(Date.UTC(year,month,0));
  return last.getUTCDate()-(last.getUTCDay()-dow+7)%7;
}
function FCN_calendarObserved(year,month,day){
  const d=new Date(Date.UTC(year,month-1,day)), weekday=d.getUTCDay();
  if(weekday===6)d.setUTCDate(d.getUTCDate()-1);
  if(weekday===0)d.setUTCDate(d.getUTCDate()+1);
  return Utilities.formatDate(d,'UTC','yyyy-MM-dd');
}
function FCN_calendarEaster(year){
  const a=year%19,b=Math.floor(year/100),c=year%100,d=Math.floor(b/4),e=b%4;
  const f=Math.floor((b+8)/25),g=Math.floor((b-f+1)/3),h=(19*a+b-d-g+15)%30;
  const i=Math.floor(c/4),k=c%4,l=(32+2*e+2*i-h-k)%7;
  const m=Math.floor((a+11*h+22*l)/451),q=h+l-7*m+114;
  return new Date(Date.UTC(year,Math.floor(q/31)-1,q%31+1));
}
function FCN_calendarUsHoliday(key){
  const y=Number(key.slice(0,4)),days=[];
  function iso(d){return Utilities.formatDate(d,'UTC','yyyy-MM-dd');}
  function add(m,d){days.push(`${y}-${String(m).padStart(2,'0')}-${String(d).padStart(2,'0')}`);}
  add(1,FCN_calendarNth(y,1,1,3)); // MLK
  add(2,FCN_calendarNth(y,2,1,3)); // Presidents
  add(5,FCN_calendarLast(y,5,1));  // Memorial
  add(9,FCN_calendarNth(y,9,1,1)); // Labor
  add(11,FCN_calendarNth(y,11,4,4)); // Thanksgiving
  for(let z=y-1;z<=y+1;z++)for(const [mo,da] of [[1,1],[6,19],[7,4],[12,25]])
    if(!(mo===1&&new Date(Date.UTC(z,0,1)).getUTCDay()===6))days.push(FCN_calendarObserved(z,mo,da));
  const easter=FCN_calendarEaster(y); easter.setUTCDate(easter.getUTCDate()-2);
  days.push(iso(easter));
  return days.includes(key);
}


function FCN_tradingDay_(day){const d=new Date(day+'T00:00:00Z');return d.getUTCDay()!==0&&d.getUTCDay()!==6&&!FCN_calendarUsHoliday(day)&&day!=='2025-01-09';}
function FCN_expectedDay_(now){
  const text=Utilities.formatDate(now,FCN_CONFIG.TIME_ZONE,'yyyy-MM-dd HH:mm'),parts=text.split(' ');
  let day=parts[0];const hm=parts[1];
  const early=new Set(['2026-11-27','2026-12-24','2027-11-26','2028-07-03','2028-11-24']);
  const cutoff=early.has(day)?'13:05':'16:05';
  let d=new Date(day+'T00:00:00Z');if(hm<cutoff)d.setUTCDate(d.getUTCDate()-1);
  for(let i=0;i<12;i++){day=d.toISOString().slice(0,10);if(FCN_tradingDay_(day))return day;d.setUTCDate(d.getUTCDate()-1);}
  throw Error('Cannot resolve market date.');
}
function FCN_hasGap_(from,to){const d=new Date(from+'T00:00:00Z');for(d.setUTCDate(d.getUTCDate()+1);d.toISOString().slice(0,10)<to;d.setUTCDate(d.getUTCDate()+1)){if(FCN_tradingDay_(d.toISOString().slice(0,10)))return true;}return false;}
