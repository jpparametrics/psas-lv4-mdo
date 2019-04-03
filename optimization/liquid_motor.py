#!/usr/bin/env python
# could improve:
# subsystem estimates
# fudge factors
# thrust estimates and curve
# print relevant data (look at the old file for figures of merit)
# idiot-proofing
# extendable file io
# make engine file with xml library

from __future__ import print_function
from math import pi, log, sqrt
import os
from sys import platform as _platform
import bodybuilder

# Physics
g_0      =     9.80665  # kg.m/s^2     Standard gravity

# Chemestry
rho_lox  =   1141.0   # kg/m^3  Desity of LOX
rho_eth  =    852.3   # kg/m^3  Desity of Ethanol (with 70% H2O)

# Tank Material
Al    = { 'rho': 2800.0,   # kg/m^3       Density
          'Sy':    0.270e9} # Pa          Yield strength
Steel = { 'rho': 7830.0,   # kg/m^3       Density
          'Sy':    0.250e9} # Pa          Yield strength
CF    = { 'rho': 1550.0,   # kg/m^3       Density
          'Sy':    0.450e9} # Pa          Yield strength

# Extra
m_engine =      3.0   # kg
l_engine =      0.300 # m
m_plumb  =      5.0   # kg
l_plumb  =      0.350 # m
gaps     =      0.100 # m

# Variables (Change these!)
loss_factor = 1    # assume thrust is less than ideal
Tank      = CF         # Choose from above table, ignore steel
factor_of_safety = 2   # factor of saftey
OF       =     1.3      #         O/F ratio

def all_files(directory):
    for path, dirs, files in os.walk(directory):
        for f in sorted(files):
            yield os.path.join(path, f)

def get_index():
    prefix = "./rocket_farm/"
    ork_files = [f for f in all_files(prefix)
               if f.endswith('.ork')]
    previous_iteration_index = len(ork_files)
    return previous_iteration_index + 1

def split_mdot(mdot):
    mdot_o = mdot / (1 + (1/OF))
    mdot_f = mdot / (1 + OF)
    return mdot_o, mdot_f

def split_prop_mass(prop_mass):
    m_o = prop_mass/(1+1/OF)
    m_f = prop_mass*(1- 1/(1+1/OF))
    return m_o, m_f

# ### Tank Geometry
#Radius of the tanks
def tank_r(total_dia):
    r = ((total_dia * 0.0254) - 0.014)/2
    return r

def tank_length(m, rho, r):
    l = m / (rho*pi*r*r)
    return l

# turn propellant mass and airframe diameter into two tanks of propellants
def split_tanks(prop_mass, total_dia):
    m_o, m_f = split_prop_mass(prop_mass)
    r = tank_r(total_dia)
    l_o = tank_length(m_o, rho_lox, r)
    l_f = tank_length(m_f, rho_eth, r)
    l_o += l_o*0.1 # add 10% for ullage
    l_f += l_f*0.1 # add 10% for ullage
    return r, l_o, l_f

# tank thickness
def tank_thickness(tank, r):
    P_i = 3.042e6  # Tank pressure in Pa, assuming pressure fed with regulator (roughly 441 psig)
    radius_o = r   # outer radius, meters
    design_stress = tank['Sy']/factor_of_safety
    radius_i = sqrt(design_stress * (radius_o**2) / ((2*P_i) + design_stress)) # inner radius
    thickness = radius_o - radius_i
    return thickness

# ### Tank Mass
def tank_mass(l, tank, r):
    s_area = 2*pi*r*(l + r) #surface area of tank
    thickness = tank_thickness(tank, r)
    material = s_area * thickness
    mass_realism_coefficient = 2 #fudge factor for design mass, includes contribution of tank structural lugs, feed system, stress concentraions, welds, slosh baffles etc.
    mass = material * tank['rho'] * mass_realism_coefficient
    return mass

def tank_builder(prop_mass, total_dia):
    r, l_o, l_f = split_tanks(prop_mass, total_dia)
    o_tank_mass = tank_mass(l_o, Al, r)
    f_tank_mass = tank_mass(l_f, Tank, r)
    return o_tank_mass, f_tank_mass

def system_length(prop_mass, total_dia):
    r, l_o, l_f = split_tanks(prop_mass, total_dia)
    return sum([l_o, l_f, l_plumb, l_engine, 3*gaps])

def system_mass(prop_mass, total_dia):
    t1, t2 = tank_builder(prop_mass, total_dia)
    return sum([m_engine, m_plumb, t1, t2])

def dry_c_of_m(prop_mass, total_dia):
    r, l_o, l_f = split_tanks(prop_mass, total_dia)
    m_tank_o, m_tank_f = tank_builder(prop_mass, total_dia)
    # lox tank cm is in the center of the tank
    cm_tank_o = l_o / 2.0

    # next tank down has a gap.
    cm_tank_f = l_o + gaps + (l_f/2.0)

    # next down
    cm_plumb = l_o + gaps + l_f + gaps +  (l_plumb/2.0)

    # finally
    cm_engine = l_o + gaps + l_f + gaps + l_plumb + gaps + (l_engine/2.0)

    # sum cm
    dry_cm = sum([cm_tank_o*m_tank_o, cm_tank_f*m_tank_f, cm_plumb*m_plumb, cm_engine*m_engine])
    dry_cm /= system_mass(prop_mass, total_dia)
    #print "Dry CM:     %0.3f m" % dry_cm
    return dry_cm

# ## Thrust Curve
# The mass and cm change over time.
# In[7]:
def mass(total_propellant, mdot, dt):
    m = total_propellant - (mdot*dt)
    return m

def c_of_m(prop_mass, total_dia, mdot, dt):
    M_o_0, M_f_0 = split_prop_mass(prop_mass)
    mdot_o, mdot_f = split_mdot(mdot)
    r, l_o, l_f = split_tanks(prop_mass, total_dia)
    dry_cm = dry_c_of_m(prop_mass, total_dia)
    dry_mass = system_mass(prop_mass, total_dia)
    
    m_o = M_o_0 - (mdot_o*dt)
    m_f = M_f_0 - (mdot_f*dt)
    
    lcm_o = l_o - tank_length(m_o, rho_lox, r)/2.0
    lcm_f = l_o + gaps + l_f - tank_length(m_f, rho_eth, r)/2.0
    
    cm_prop = ((m_o*lcm_o) + (m_f*lcm_f))/(m_o + m_f+0.000001)
    cm = ((dry_cm*dry_mass) + (cm_prop*(m_f+m_o)))/(dry_mass+m_f+m_o)
    return cm

# In[8]:
# NAR letter code
def nar_code(thrust, burn_time):
    impulse = thrust*burn_time
    print("")
    print("Total impulse:    %0.0f N.s" % impulse)

    nar_i = int(log(impulse/2.5)/log(2))
    nar_percent = impulse/(2.5*2**(nar_i+1))
    print('NAR:              "%s" (%0.0f%%)' % (chr(66+nar_i), nar_percent*100))
    return chr(66+nar_i), nar_percent*100

def print_characteristics(mdot, prop_mass, r, l_o, l_f, index, res_text):
    # Mass flow for each propllent
    mdot_o = mdot / (1 + (1/OF))
    mdot_f = mdot / (1 + OF)
    res_text.append("\nOx flow: . . . . . . . %7.3f kg/s" % mdot_o)
    res_text.append("\nFuel flow:             %7.3f kg/s" % mdot_f)
    # Propellent Mass for each propllent
    mdot_o = prop_mass / (1 + (1/OF))
    mdot_f = prop_mass / (1 + OF)
    res_text.append("\nOx mass:               %5.1f kg" % M_o)
    res_text.append("\nFuel mass: . . . . . . %5.1f kg" % M_f)
    # dimensions of each tank
    res_text.append("\nTank diameters:        %7.3 m" % r*2)
    res_text.append("\nOx tank length: . . . .%7.3f m" % l_o)
    res_text.append("\nFuel tank length:      %7.3f m" % l_f)
    # Tank thickness for each tank (mm)
    thickness_o = tank_thickness(Al, r)
    thickness_f = tank_thickness(Tank, r)
    res_text.append("\nOx tank thickness:        %5.1f mm" % (thickness_o*1000))
    res_text.append("\nFuel tank thickness:        %5.1f mm" % (thickness_f*1000))
    # Mass of each tank
    m_tank_o = tank_mass(l_o, Al)
    m_tank_f = tank_mass(l_f, Tank)
    res_text.append("\nOx tank mass: . . . . .%5.1f kg" % m_tank_o)
    res_text.append("\nFuel tank mass:        %5.1f kg" % m_tank_f)
    with open('./rocket_farm/'+'psas_rocket_'+index+'_traj.txt', 'w') as traj:
        for line in res_text:
            traj.write(line)
        traj.close()
    
    

def make_engine(mdot, prop_mass, total_dia, Thrust, Burn_time, Isp, res_text):
    index = str(get_index())
    r, l_o, l_f = split_tanks(prop_mass, total_dia)
    print_characteristics(mdot, prop_mass, r, l_o, l_f, index, res_text)
    Thrust *= loss_factor
    length = system_length(prop_mass, total_dia)
    M_prop = prop_mass
    dry_mass = system_mass(prop_mass, total_dia)
    file_head = """<engine-database>
  <engine-list>
    <engine  mfg="PSAS" code="{code}" Type="Liquid" dia="{diameter}" len="{length}"
    initWt="{total_mass}" propWt="{M_prop}" delays="0" auto-calc-mass="0" auto-calc-cg="0"
    avgThrust="{thrust}" peakThrust="{thrust}" throatDia="0." exitDia="0." Itot="{impulse}"
    burn-time="{burn_time}" massFrac="{m_frac}" Isp="{Isp}" tDiv="10" tStep="-1." tFix="1"
    FDiv="10" FStep="-1." FFix="1" mDiv="10" mStep="-1." mFix="1" cgDiv="10"
    cgStep="-1." cgFix="1">
    <comments>Made up</comments>
    <data>
""".format(**{'code': 'PSAS'+index,
                  'diameter': r*2*1000,
                  'length': length*1000,
                  'total_mass': (M_prop+dry_mass)*1000,
                  'M_prop': M_prop*1000,
                  'thrust': Thrust,
                  'burn_time': Burn_time,
                  'm_frac': dry_mass/(dry_mass+M_prop)*1000,
                  'impulse': Thrust*Burn_time,
                  'Isp': Isp,
        })
    
    data = []
    n = 100
    res = Burn_time/float(n-1)
    for i in range(n):
        t = i * res
        data.append('     <eng-data  t="{t}" f="{thrust}" m="{mass}" cg="{cg}"/>\n'.format(**{
            't': t,
            'thrust': Thrust,
            'mass': dry_mass*1000 + mass(M_prop, mdot, t)*1000,
            'cg': c_of_m(M_prop, total_dia, mdot, t)*1000,
        }))
    
    file_tail = """
    </data>
  </engine>
</engine-list>
</engine-database>"""
    
    prefix = "./"
    if 'linux' in _platform:
        home = os.path.expanduser("~")
        prefix =  os.path.join(home, '.openrocket/ThrustCurves/')
    elif _platform == "darwin":
        home = os.path.expanduser("~")
        prefix =  os.path.join(home, 'Library/Application Support/OpenRocket/ThrustCurves/')
    elif "win" in _platform:
        prefix = os.path.join(os.getenv("APPDATA"), "OpenRocket/ThrustCurves/")
    
    with open(os.path.join(prefix, 'psas_motor_'+index+'.rse'), 'w') as eng:
        eng.write(file_head)
        for d in data:
            eng.write(d)
        eng.write(file_tail)
        eng.close()
    bodybuilder.update_body(index, r, l_o, l_f)
    print("Reopen OpenRocket to run simulation")
    