// User-supplied v1.0 source, 2026-10-17. Formatting/comments condensed only.
// This is not an export of the inaccessible live project. Keep the live export too.
const FCN_CONFIG = Object.freeze({
  SPREADSHEET_ID:'1ef0Whr7-bgj37DdOnC7ug8Dyv5Ab92-AMw5n9V18UJY',
  MATRIX:'收盤價矩陣',STAGING:'FCN_每日股價暫存',SNAPSHOT:'FCN_行情值快照',
  STATUS:'FCN_同步狀態',LOG:'更新紀錄',TIME_ZONE:'America/New_York',
  BATCH_SIZE:40,HISTORY_DAYS:27,STAGING_ROWS:100,MIN_READY_RATE:0.60,
  PROPS_CURSOR:'FCN_STOCK_BATCH_CURSOR',PROPS_STAGE:'FCN_STOCK_STAGE_ACTIVE',
  PROPS_LOOKBACK:'FCN_STOCK_LOOKBACK_DAYS'
});
function FCN_install(){
  const ss=SpreadsheetApp.openById(FCN_CONFIG.SPREADSHEET_ID);
  const {matrix,tickers}=FCN_getSource_(ss);
  if(matrix.getLastRow()<2||tickers.length<2)throw Error('找不到正式歷史價矩陣與股票表頭；為保護原表，安裝停止。');
  FCN_getOrCreateStage_(ss);FCN_getOrCreateSnapshot_(ss);FCN_getOrCreateStatus_(ss);
  ScriptApp.getProjectTriggers().filter(t=>t.getHandlerFunction()==='FCN_hourlyJob').forEach(t=>ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('FCN_hourlyJob').timeBased().everyHours(1).create();
  const props=PropertiesService.getScriptProperties();
  props.setProperty(FCN_CONFIG.PROPS_CURSOR,'0');props.deleteProperty(FCN_CONFIG.PROPS_STAGE);props.deleteProperty(FCN_CONFIG.PROPS_LOOKBACK);
  FCN_hourlyJob();
  SpreadsheetApp.getActive().toast('已安裝每小時分批更新；約 14 小時涵蓋全庫 526 個股票欄位。','FCN 股價同步',8);
}
function FCN_hourlyJob(){
  const lock=LockService.getScriptLock();if(!lock.tryLock(5000))return;
  try{FCN_hourlyJobUnlocked_();}catch(err){FCN_recordError_(String(err&&err.message?err.message:err));throw err;}finally{lock.releaseLock();}
}
function FCN_hourlyJobUnlocked_(){
  const ss=SpreadsheetApp.openById(FCN_CONFIG.SPREADSHEET_ID),{matrix,tickers}=FCN_getSource_(ss);
  const stage=FCN_getOrCreateStage_(ss),snapshot=FCN_getOrCreateSnapshot_(ss),props=PropertiesService.getScriptProperties();
  const now=new Date(),today=Utilities.formatDate(now,FCN_CONFIG.TIME_ZONE,'yyyy-MM-dd');
  let saved=0,datesAdded=0,issues=[],batchRead=0;
  const active=props.getProperty(FCN_CONFIG.PROPS_STAGE);
  if(active){
    const meta=JSON.parse(active),width=meta.symbols.length*2;
    stage.getRange(1,1,FCN_CONFIG.STAGING_ROWS,width).copyTo(snapshot.getRange(1,1,FCN_CONFIG.STAGING_ROWS,width),SpreadsheetApp.CopyPasteType.PASTE_VALUES,false);
    const grid=snapshot.getRange(1,1,FCN_CONFIG.STAGING_ROWS,width).getValues();
    const parsed=FCN_parseStage_(grid,meta.symbols,today);batchRead=meta.symbols.length;issues=parsed.issues;
    const result=FCN_mergeIntoMatrix_(matrix,tickers,parsed.byDay,meta.symbols);saved=result.saved;datesAdded=result.datesAdded;
    if(result.holes.length)issues.push('既有交易日缺漏：'+result.holes.slice(0,4).join('、'));
    if(saved>0||datesAdded>0){
      const log=ss.getSheetByName(FCN_CONFIG.LOG);
      if(log){const next=log.getLastRow()+1;FCN_ensureRows_(log,next);log.getRange(next,1,1,7).setValues([[
        Utilities.formatDate(now,FCN_CONFIG.TIME_ZONE,'yyyy-MM-dd HH:mm:ss'),'每日增量固定價（Apps Script 分批）',
        result.firstDay+'～'+result.lastDay,batchRead,saved,'成功'+(issues.length?'／部分缺價待重試':''),
        'GOOGLEFINANCE → 收盤價矩陣固定值（僅填空白）']]);}
    }
  }
  let cursor=Number(props.getProperty(FCN_CONFIG.PROPS_CURSOR)||0);
  if(!Number.isInteger(cursor)||cursor<0||cursor>=tickers.length)cursor=0;
  const nextSymbols=tickers.slice(cursor,cursor+FCN_CONFIG.BATCH_SIZE);
  const lookback=Number(props.getProperty(FCN_CONFIG.PROPS_LOOKBACK)||FCN_CONFIG.HISTORY_DAYS);
  FCN_writeNextStage_(stage,nextSymbols,lookback);
  props.setProperty(FCN_CONFIG.PROPS_STAGE,JSON.stringify({symbols:nextSymbols}));
  props.setProperty(FCN_CONFIG.PROPS_CURSOR,String((cursor+nextSymbols.length)%tickers.length));
  const lastDate=FCN_matrixDates_(matrix).slice(-1)[0]||'無';
  FCN_writeStatus_(ss,[
    ['最後執行時間（紐約）',Utilities.formatDate(now,FCN_CONFIG.TIME_ZONE,'yyyy-MM-dd HH:mm:ss')],
    ['排程','每小時分批；每日輪巡所有股票；不需要 GitHub Secret'],['歷史試打矩陣最後日期',lastDate],
    ['本次新增交易日',datesAdded],['本次固定新增價格筆數',saved],['本次讀入的股票檔數',batchRead],
    ['下一批股票',nextSymbols[0]+' ～ '+nextSymbols[nextSymbols.length-1]],['下一批進度',`${cursor+1}～${cursor+nextSymbols.length} / ${tickers.length}`],
    ['缺價／品質提醒',issues.length?issues.slice(0,8).join('；'):'無（單一標的無價會留白，不造價）'],
    ['同步狀態',batchRead&&issues.length===batchRead?'警告：本批無有效日期化價格，可能受 GOOGLEFINANCE 歷史資料讀取限制；尚未入庫':'本輪已執行；須核對最新日期與更新紀錄確認入庫']]);
}
function FCN_parseStage_(grid,symbols,today){
  const byDay=new Map(),issues=[];
  symbols.forEach((ticker,i)=>{
    const col=i*2;if(String(grid[0][col]||'')!==ticker){issues.push(ticker+' 暫存表頭不一致');return;}
    let n=0;
    for(let r=2;r<grid.length;r++){
      const day=FCN_dateKey_(grid[r][col]),val=grid[r][col+1],price=Number(val);
      if(!day||day>=today||!Number.isFinite(price)||price<=0||val==='')continue;
      if(!byDay.has(day))byDay.set(day,new Map());byDay.get(day).set(ticker,price);n++;
    }
    if(!n)issues.push(ticker+' 未取得日期化收盤價');
  });return {byDay,issues};
}
function FCN_mergeIntoMatrix_(matrix,tickers,byDay,stagedSymbols){
  const existing=FCN_matrixDates_(matrix),index=new Map(existing.map((day,i)=>[day,i+2]));
  let latest=existing.length?existing[existing.length-1]:'',saved=0;
  const holes=[],addedDays=[],required=Math.max(3,Math.floor(stagedSymbols.length*FCN_CONFIG.MIN_READY_RATE)),days=Array.from(byDay.keys()).sort();
  let deferredNewDate=false;
  const columns=stagedSymbols.map(sym=>{const j=tickers.indexOf(sym);if(j<0)throw Error('股票欄位不在原矩陣表頭：'+sym);return j+2;});
  days.forEach(day=>{
    const quotes=byDay.get(day);let row=index.get(day);
    if(!row){
      if(latest&&day<=latest){holes.push(day);return;}
      if(deferredNewDate||quotes.size<required){deferredNewDate=true;return;}
      row=matrix.getLastRow()+1;FCN_ensureRows_(matrix,row);matrix.getRange(row,1).setValue(day);index.set(day,row);addedDays.push(day);latest=day;
    }
    const minColumn=columns[0],count=columns.length,old=matrix.getRange(row,minColumn,1,count).getValues()[0];
    let runStart=-1,runValues=[];
    function flush(){if(runStart>=0){matrix.getRange(row,minColumn+runStart,1,runValues.length).setValues([runValues]);saved+=runValues.length;}runStart=-1;runValues=[];}
    for(let i=0;i<count;i++){const quote=quotes.get(stagedSymbols[i]),blank=old[i]===''||old[i]===null;
      if(blank&&Number.isFinite(quote)&&quote>0){if(runStart<0)runStart=i;runValues.push(quote);}else flush();
    }flush();
  });return {saved,datesAdded:addedDays.length,firstDay:days[0]||'',lastDay:days[days.length-1]||'',holes};
}
function FCN_writeNextStage_(stage,symbols,lookback){
  const width=2*FCN_CONFIG.BATCH_SIZE;stage.getRange(1,1,FCN_CONFIG.STAGING_ROWS,width).clearContent();
  const head=Array(width).fill(''),formulas=Array(width).fill('');
  symbols.forEach((sym,i)=>{
    if(!/^[A-Z0-9.^_-]{1,18}$/.test(sym))throw Error('股票代號格式無法安全形成 GOOGLEFINANCE 公式：'+sym);
    head[2*i]=sym;formulas[2*i]=`=GOOGLEFINANCE("${sym}","close",TODAY()-${lookback},TODAY(),"DAILY")`;
  });
  stage.getRange(1,1,1,width).setValues([head]);stage.getRange(2,1,1,width).setValues([formulas]);SpreadsheetApp.flush();
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
    if(!d){if(rows[i][0]!==''&&rows[i][0]!==null)throw Error('正式矩陣第'+(i+2)+'列日期錯誤');continue;}
    if(dates.length&&d<=dates[dates.length-1])throw Error('原始日期未遞增，拒絕追加或改動');dates.push(d);
  }return dates;
}
function FCN_dateKey_(value){
  if(value instanceof Date&&!isNaN(value.getTime()))return Utilities.formatDate(value,FCN_CONFIG.TIME_ZONE,'yyyy-MM-dd');
  if(typeof value==='number'&&Number.isFinite(value)&&value>20000&&value<100000){
    const d=new Date(Date.UTC(1899,11,30)+Math.floor(value)*86400000);return Utilities.formatDate(d,'UTC','yyyy-MM-dd');
  }
  const s=String(value==null?'':value).trim().replace(/\//g,'-');
  if(/^\d{4}-\d{2}-\d{2}$/.test(s)&&!isNaN(Date.parse(s+'T00:00:00Z')))return s;return '';
}
function FCN_ensureRows_(sheet,lastNeeded){if(sheet.getMaxRows()<lastNeeded)sheet.insertRowsAfter(sheet.getMaxRows(),Math.max(50,lastNeeded-sheet.getMaxRows()));}
function FCN_backfillLast90Days(){PropertiesService.getScriptProperties().setProperty(FCN_CONFIG.PROPS_LOOKBACK,'90');FCN_hourlyJob();}
function FCN_stop(){
  ScriptApp.getProjectTriggers().filter(t=>t.getHandlerFunction()==='FCN_hourlyJob').forEach(t=>ScriptApp.deleteTrigger(t));
  SpreadsheetApp.getActive().toast('自動同步已停止；正式歷史價格沒有更動。','FCN 股價同步',8);
}
function onOpen(){
  SpreadsheetApp.getUi().createMenu('FCN 股價庫').addItem('啟用每日自動固定股價','FCN_install').addItem('立即執行一輪','FCN_hourlyJob').addItem('回補最近90天','FCN_backfillLast90Days').addSeparator().addItem('停止自動更新','FCN_stop').addToUi();
}
