package org.beyondlight;
import java.util.*;
/** SI classical mechanics, selected EM/thermal relations, and special relativity. */
public final class Physics {
 public static final double C=ScientificCatalog.value("c"),G=ScientificCatalog.value("G"),EPS0=ScientificCatalog.value("epsilon_0"),MU0=ScientificCatalog.value("mu_0");
 public record Relativistic(double gamma,double properTimeS,double contractedLengthM,double momentumKgMps,double kineticEnergyJ,double totalEnergyJ,double energyMomentumResidualJ2){}
 private Physics(){}
 public static double gamma(double v){if(!Double.isFinite(v)||Math.abs(v)>=C)throw new IllegalArgumentException("speed must be finite and |v| < c");return 1/Math.sqrt(1-v*v/(C*C));}
 public static Relativistic relativity(double mass,double v,double dt,double length){if(mass<0||!Double.isFinite(mass)||dt<0||!Double.isFinite(dt)||length<0||!Double.isFinite(length))throw new IllegalArgumentException("mass, time and length must be finite and nonnegative");double g=gamma(v),p=g*mass*v,e=g*mass*C*C,k=(g-1)*mass*C*C;return new Relativistic(g,dt/g,length/g,p,k,e,e*e-p*p*C*C-mass*mass*Math.pow(C,4));}
 public static double addVelocity(double u,double v){gamma(u);gamma(v);double w=(u+v)/(1+u*v/(C*C));gamma(w);return w;}
 public static double gravitation(double m1,double m2,double r){if(m1<0||m2<0||r<=0)throw new IllegalArgumentException("masses nonnegative and separation positive required");return G*m1*m2/(r*r);}
 public static double lorentzForceMagnitude(double q,double[]v,double[]e,double[]b){if(v.length!=3||e.length!=3||b.length!=3)throw new IllegalArgumentException("3D vectors required");double[]cross={v[1]*b[2]-v[2]*b[1],v[2]*b[0]-v[0]*b[2],v[0]*b[1]-v[1]*b[0]};double n=0;for(int i=0;i<3;i++)n+=Math.pow(q*(e[i]+cross[i]),2);return Math.sqrt(n);}
 public static double conductionPower(double conductivity,double area,double deltaT,double thickness){if(conductivity<0||area<0||thickness<=0)throw new IllegalArgumentException("k and area nonnegative, thickness positive");return conductivity*area*deltaT/thickness;}
 public static double radiativePower(double emissivity,double area,double temp,double ambient){if(emissivity<0||emissivity>1||area<0||temp<0||ambient<0)throw new IllegalArgumentException("invalid radiation parameters");return emissivity*ScientificCatalog.value("sigma_SB")*area*(Math.pow(temp,4)-Math.pow(ambient,4));}
}
