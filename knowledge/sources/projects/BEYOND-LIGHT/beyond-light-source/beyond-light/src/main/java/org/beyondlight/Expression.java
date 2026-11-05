package org.beyondlight;
import java.util.*;
/** Bounded recursive-descent evaluator for arithmetic expressions, variables and sqrt/ln/exp/sin/cos. */
public final class Expression {
 private final String s; private int p;
 private Expression(String s){this.s=s;}
 public static double evaluate(String text,Map<String,Double> vars){if(text.length()>4096)throw new IllegalArgumentException("expression exceeds 4096 characters");Expression e=new Expression(text);double v=e.sum(vars);e.ws();if(e.p!=text.length())throw e.error("unexpected token");if(!Double.isFinite(v))throw new IllegalArgumentException("result is not finite");return v;}
 private double sum(Map<String,Double> v){double x=product(v);while(true){ws();if(take('+'))x+=product(v);else if(take('-'))x-=product(v);else return x;}}
 private double product(Map<String,Double> v){double x=power(v);while(true){ws();if(take('*'))x*=power(v);else if(take('/')){double d=power(v);if(d==0)throw error("division by zero");x/=d;}else return x;}}
 private double power(Map<String,Double> v){double x=unary(v);ws();if(take('^'))x=Math.pow(x,power(v));return x;}
 private double unary(Map<String,Double> v){ws();if(take('+'))return unary(v);if(take('-'))return -unary(v);if(take('(')){double x=sum(v);ws();if(!take(')'))throw error("expected )");return x;}if(p<s.length()&&(Character.isDigit(s.charAt(p))||s.charAt(p)=='.'))return number();String id=ident();if(id.isEmpty())throw error("expected number, variable, or function");if(id.equals("pi"))return Math.PI;if(id.equals("e"))return Math.E;ws();if(take('(')){double a=sum(v);ws();if(!take(')'))throw error("expected )");return switch(id){case "sqrt"->Math.sqrt(a);case "ln"->Math.log(a);case "exp"->Math.exp(a);case "sin"->Math.sin(a);case "cos"->Math.cos(a);default->throw error("unknown function "+id);};}if(!v.containsKey(id))throw error("undefined variable "+id);return v.get(id);}
 private String ident(){ws();int a=p;while(p<s.length()&&(Character.isLetterOrDigit(s.charAt(p))||s.charAt(p)=='_'))p++;return s.substring(a,p);}
 private double number(){int a=p;while(p<s.length()&&(Character.isDigit(s.charAt(p))||".eE".indexOf(s.charAt(p))>=0)){if((s.charAt(p)=='+'||s.charAt(p)=='-')&&p>a&&"eE".indexOf(s.charAt(p-1))<0)break;p++;}try{return Double.parseDouble(s.substring(a,p));}catch(Exception ex){throw error("invalid number");}}
 private void ws(){while(p<s.length()&&Character.isWhitespace(s.charAt(p)))p++;} private boolean take(char c){if(p<s.length()&&s.charAt(p)==c){p++;return true;}return false;}private IllegalArgumentException error(String m){return new IllegalArgumentException(m+" at column "+(p+1));}
}
