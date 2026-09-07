import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";
const src=await readFile(new URL("../src/silk-color-names.ts", import.meta.url),"utf8");
const js=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {silkColorNames,silkColorName,formatSilkColor,matchesSilkColor}=await import("data:text/javascript;base64,"+Buffer.from(js).toString("base64"));
test("46 approved names are unique; special CSK formula remains unchanged",()=>{
 assert.equal(Object.keys(silkColorNames).length,46);
 assert.equal(new Set(Object.values(silkColorNames)).size,46);
 assert.equal(silkColorName("CSK 18/16-2/3"),"Коралова глина");
 assert.equal(formatSilkColor("CSK 01-2"),"Світлий льон · CSK 01-2");
 assert.equal(formatSilkColor("unknown"),"unknown");
});
test("search supports codes, names, case and Ukrainian apostrophes",()=>{
 assert.ok(matchesSilkColor("CSK 03-32","шавлія"));
 assert.ok(matchesSilkColor("CSK 03-32","csk03-32"));
 assert.ok(matchesSilkColor("CSK 04-1","м'ятна"));
 assert.ok(!matchesSilkColor("CSK 01-2","шавлія"));
});
test("only Silk presentation changes; sending continues to use asset IDs",async()=>{
 const ui=await readFile(new URL("../src/pages/MediaLibraryPicker.tsx",import.meta.url),"utf8");
 assert.match(ui,/material === "Мокрий шовк" \? matchesSilkColor/);
 assert.match(ui,/item_ids: picked/);
 assert.match(ui,/code ===/);
 assert.match(ui,/isColorSwatch/);
});

