/* Beyond-Light bounded symbolic engine.
 * Browser port of the supported grammar and transformations in Expression.java
 * and Symbolic.java. No eval(), network access, or dynamic code execution.
 */
(() => {
  "use strict";
  const FUNCTIONS = new Set(["sqrt", "ln", "exp", "sin", "cos"]);
  const MAX_LENGTH = 4096;

  function tokenize(source) {
    if (typeof source !== "string" || !source.trim() || source.length > MAX_LENGTH) {
      throw new Error("Ekspresi kosong atau melebihi 4096 karakter.");
    }
    const tokens = [];
    let i = 0;
    while (i < source.length) {
      const ch = source[i];
      if (/\s/.test(ch)) { i++; continue; }
      const rest = source.slice(i);
      const number = rest.match(/^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?/);
      if (number) { tokens.push({type:"number", value:Number(number[0])}); i += number[0].length; continue; }
      const ident = rest.match(/^[A-Za-z_][A-Za-z0-9_]*/);
      if (ident) { tokens.push({type:"id", value:ident[0]}); i += ident[0].length; continue; }
      if ("+-*/^()".includes(ch)) { tokens.push({type:ch, value:ch}); i++; continue; }
      throw new Error("Karakter tidak dikenal pada posisi " + (i + 1) + ".");
    }
    tokens.push({type:"eof"});
    return tokens;
  }

  function parse(source) {
    const ts = tokenize(source); let p = 0;
    const peek = () => ts[p], take = type => {
      if (peek().type !== type) throw new Error("Diharapkan '" + type + "' pada token " + (p + 1) + ".");
      return ts[p++];
    };
    function primary() {
      if (peek().type === "+") { take("+"); return primary(); }
      if (peek().type === "-") { take("-"); return {op:"neg", a:primary()}; }
      if (peek().type === "number") return {op:"num", n:take("number").value};
      if (peek().type === "(") { take("("); const n=sum(); take(")"); return n; }
      if (peek().type === "id") {
        const name=take("id").value;
        if (peek().type === "(") {
          if (!FUNCTIONS.has(name)) throw new Error("Fungsi tidak didukung: " + name);
          take("("); const a=sum(); take(")"); return {op:name,a};
        }
        return {op:"var",name};
      }
      throw new Error("Diharapkan angka, variabel, fungsi, atau tanda kurung.");
    }
    function power() { let n=primary(); if(peek().type==="^"){take("^");n={op:"^",a:n,b:power()};} return n; }
    function product() { let n=power(); while(peek().type==="*"||peek().type==="/"){const op=ts[p++].type;n={op,a:n,b:power()};} return n; }
    function sum() { let n=product(); while(peek().type==="+"||peek().type==="-"){const op=ts[p++].type;n={op,a:n,b:product()};} return n; }
    const ast=sum(); if(peek().type!=="eof") throw new Error("Token berlebih setelah ekspresi.");
    return simplify(ast);
  }
  const num = n => n.op==="num";
  const C = n => ({op:"num",n});
  const V = name => ({op:"var",name});
  function simplify(n) {
    if (!n.a) return n;
    const a=simplify(n.a), b=n.b?simplify(n.b):null;
    if(n.op==="neg"){if(num(a))return C(-a.n);if(a.op==="neg")return a.a;return {op:"neg",a};}
    if(b && num(a)&&num(b)){
      const z=({"+":()=>a.n+b.n,"-":()=>a.n-b.n,"*":()=>a.n*b.n,"/":()=>a.n/b.n,"^":()=>Math.pow(a.n,b.n)})[n.op]();
      if(Number.isFinite(z))return C(z);
    }
    if(n.op==="+"&&num(a)&&a.n===0)return b;
    if(n.op==="+"&&num(b)&&b.n===0)return a;
    if(n.op==="-"&&num(b)&&b.n===0)return a;
    if(n.op==="*"&&((num(a)&&a.n===0)||(num(b)&&b.n===0)))return C(0);
    if(n.op==="*"&&num(a)&&a.n===1)return b;
    if(n.op==="*"&&num(b)&&b.n===1)return a;
    if(n.op==="/"&&num(b)&&b.n===1)return a;
    if(n.op==="^"&&num(b)&&b.n===1)return a;
    if(n.op==="^"&&num(b)&&b.n===0)return C(1);
    return {op:n.op,a,b};
  }
  function print(n) {
    if(n.op==="num")return Number(n.n.toPrecision(12)).toString();
    if(n.op==="var")return n.name;
    if(n.op==="neg")return "(-"+print(n.a)+")";
    if(!n.b)return n.op+"("+print(n.a)+")";
    return "("+print(n.a)+n.op+print(n.b)+")";
  }
  function evaluate(n, vars) {
    if(n.op==="num")return n.n;
    if(n.op==="var"){
      if(n.name==="pi")return Math.PI;if(n.name==="e")return Math.E;
      if(!Object.prototype.hasOwnProperty.call(vars,n.name))throw new Error("Variabel belum diberi nilai: "+n.name);
      const v=Number(vars[n.name]);if(!Number.isFinite(v))throw new Error("Nilai variabel harus finite.");return v;
    }
    const a=evaluate(n.a,vars);let out;
    if(n.op==="neg")out=-a;
    else if(!n.b)out=({sqrt:Math.sqrt,ln:Math.log,exp:Math.exp,sin:Math.sin,cos:Math.cos})[n.op](a);
    else {const b=evaluate(n.b,vars);out=({"+":()=>a+b,"-":()=>a-b,"*":()=>a*b,"/":()=>{if(b===0)throw new Error("Pembagian dengan nol.");return a/b;},"^":()=>Math.pow(a,b)})[n.op]();}
    if(!Number.isFinite(out))throw new Error("Hasil berada di luar domain bilangan real finite.");
    return out;
  }
  function has(n,x){return (n.op==="var"&&n.name===x)||(n.a&&has(n.a,x))||(n.b&&has(n.b,x));}
  function derivative(n,x){
    if(n.op==="num"||(n.op==="var"&&n.name!==x))return C(0);
    if(n.op==="var")return C(1);
    const a=n.a,b=n.b,da=derivative(a,x),db=b?derivative(b,x):null;
    switch(n.op){
      case "neg":return {op:"neg",a:da};
      case "+":case "-":return {op:n.op,a:da,b:db};
      case "*":return {op:"+",a:{op:"*",a:da,b},b:{op:"*",a,b:db}};
      case "/":return {op:"/",a:{op:"-",a:{op:"*",a:da,b},b:{op:"*",a,b:db}},b:{op:"^",a:b,b:C(2)}};
      case "^":
        if(has(b,x))throw new Error("Turunan pangkat dengan eksponen variabel belum didukung.");
        return {op:"*",a:{op:"*",a:b,b:{op:"^",a,b:{op:"-",a:b,b:C(1)}}},b:da};
      case "sin":return {op:"*",a:{op:"cos",a},b:da};
      case "cos":return {op:"neg",a:{op:"*",a:{op:"sin",a},b:da}};
      case "exp":return {op:"*",a:{op:"exp",a},b:da};
      case "ln":return {op:"/",a:da,b:a};
      case "sqrt":return {op:"/",a:da,b:{op:"*",a:C(2),b:{op:"sqrt",a}}};
      default:throw new Error("Turunan tidak didukung untuk "+n.op);
    }
  }
  function integrate(n,x){
    if(n.op==="num")return {op:"*",a:n,b:V(x)};
    if(n.op==="var"&&n.name===x)return {op:"/",a:{op:"^",a:V(x),b:C(2)},b:C(2)};
    if(n.op==="var"||!has(n,x))return {op:"*",a:n,b:V(x)};
    if(n.op==="+"||n.op==="-")return {op:n.op,a:integrate(n.a,x),b:integrate(n.b,x)};
    if(n.op==="^"&&n.a.op==="var"&&n.a.name===x&&num(n.b)&&n.b.n!==-1){
      const k=n.b.n+1;return {op:"/",a:{op:"^",a:V(x),b:C(k)},b:C(k)};
    }
    throw new Error("Integral terbatas: konstanta, x, penjumlahan/pengurangan, dan x^n (n ≠ -1).");
  }
  function substitute(n, variable, replacement) {
    if(n.op==="var"&&n.name===variable)return replacement;
    if(!n.a)return n;
    const out={op:n.op,a:substitute(n.a,variable,replacement)};
    if(n.b)out.b=substitute(n.b,variable,replacement);
    return simplify(out);
  }
  function solveFor(expr, variable, rhs) {
    if(expr.op==="var"&&expr.name===variable)return rhs;
    if(expr.b&&has(expr.a,variable)&&!has(expr.b,variable)){
      const z=expr.b;
      switch(expr.op){
        case "+":return solveFor(expr.a,variable,simplify({op:"-",a:rhs,b:z}));
        case "-":return solveFor(expr.a,variable,simplify({op:"+",a:rhs,b:z}));
        case "*":return solveFor(expr.a,variable,simplify({op:"/",a:rhs,b:z}));
        case "/":return solveFor(expr.a,variable,simplify({op:"*",a:rhs,b:z}));
        case "^":
          if(!num(z))throw new Error("Isolasi eksponen variabel belum didukung.");
          if(z.n===0)throw new Error("Eksponen nol tidak dapat dibalik untuk isolasi.");
          return solveFor(expr.a,variable,simplify({op:"^",a:rhs,b:C(1/z.n)}));
        default:throw new Error("Operasi tidak dapat dibalik untuk isolasi.");
      }
    }
    if(expr.b&&has(expr.b,variable)&&!has(expr.a,variable)){
      const z=expr.a;
      switch(expr.op){
        case "+":return solveFor(expr.b,variable,simplify({op:"-",a:rhs,b:z}));
        case "-":return solveFor(expr.b,variable,simplify({op:"-",a:z,b:rhs}));
        case "*":return solveFor(expr.b,variable,simplify({op:"/",a:rhs,b:z}));
        case "/":return solveFor(expr.b,variable,simplify({op:"/",a:z,b:rhs}));
        default:throw new Error("Operasi sisi kanan tidak dapat dibalik untuk isolasi.");
      }
    }
    if(!expr.b&&expr.a&&has(expr.a,variable)){
      let inverse;
      if(expr.op==="sqrt")inverse={op:"^",a:rhs,b:C(2)};
      else if(expr.op==="ln")inverse={op:"exp",a:rhs};
      else if(expr.op==="exp")inverse={op:"ln",a:rhs};
      else throw new Error("Fungsi tidak memiliki invers yang didukung untuk isolasi.");
      return solveFor(expr.a,variable,simplify(inverse));
    }
    throw new Error("Variabel target tidak berada pada ekspresi invertibel yang didukung.");
  }
  function isolate(lhs, rhs, variable) {
    const left=parse(lhs),right=parse(rhs);
    const inLeft=has(left,variable),inRight=has(right,variable);
    if(inLeft===inRight)throw new Error("Isolasi memerlukan variabel target tepat pada satu sisi persamaan.");
    return print(simplify(inLeft?solveFor(left,variable,right):solveFor(right,variable,left)));
  }
  function analyze(expression, variable, value) {
    const ast=parse(expression), out={canonical:print(ast),variable:variable||"x"};
    if(value!==""&&value!==null&&value!==undefined)out.value=evaluate(ast,{[out.variable]:Number(value)});
    try{out.derivative=print(simplify(derivative(ast,out.variable)));}catch(e){out.derivativeUnavailable=e.message;}
    try{out.integral=print(simplify(integrate(ast,out.variable)))+" + C";}catch(e){out.integralUnavailable=e.message;}
    return out;
  }
  window.BeyondLightSymbolic={parse,print,evaluate,analyze,derivative,integrate,simplify,substitute:(expression,variable,replacement)=>print(substitute(parse(expression),variable,parse(replacement))),isolate};
})();
