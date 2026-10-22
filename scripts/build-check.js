'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm'),{spawnSync}=require('child_process');
for(const file of ['app.js','organizer.js','event-redirect.js','zodiac-theme.js']){
 new vm.Script(fs.readFileSync(path.join('public',file),'utf8'),{filename:file});console.log('JavaScript syntax OK:',file);
}
for(const file of ['index.html','play.html','event-ended.html','organizer.html']){
 const html=fs.readFileSync(path.join('public',file),'utf8');
 for(const match of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)){
  if(/\bsrc\s*=|type\s*=\s*["']module/i.test(match[1]))continue;
  new vm.Script(match[2],{filename:file});
 }
 console.log('HTML inline JavaScript OK:',file);
}
const config=JSON.parse(fs.readFileSync('vercel.json','utf8'));if(config.framework!=='flask'||config.cleanUrls!==true)throw Error('Vercel Flask/clean URL configuration missing');
const python=process.env.PYTHON||(fs.existsSync('.venv/bin/python')?'.venv/bin/python':'python');
// Always isolate build tests from ALL production credentials. test_app.py supplies a temporary database.
const env={...process.env};delete env.DATABASE_URL;delete env.VERCEL;delete env.RUN_POSTGRES_TESTS;
const result=spawnSync(python,['-m','unittest','discover','-s','tests','-v'],{stdio:'inherit',env});
if(result.error)throw result.error;if(result.status!==0)process.exit(result.status||1);
console.log('Build validation PASSED. This Flask application has no frontend compilation step.');
