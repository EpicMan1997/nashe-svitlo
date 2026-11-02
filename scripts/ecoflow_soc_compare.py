#!/usr/bin/env python3
"""One-off BMS cross-check, never logs SN or private device labels."""
import os
from ecoflow_probe import DEVICE_LIST, DEVICE_QUOTA, extract_devices, request_api, safe_model
from ecoflow_live_normalize import nested_get
def main():
    access=os.environ["ECOFLOW_ACCESS_KEY"]; secret=os.environ["ECOFLOW_SECRET_KEY"]
    devices=extract_devices(request_api(DEVICE_LIST,access,secret))
    d2=0
    for device in devices:
        if not isinstance(device,dict):continue
        model=safe_model(device)
        if model not in ("DELTA 2","DELTA Pro 3"):continue
        if model=="DELTA 2":d2+=1
        quota=request_api(DEVICE_QUOTA,access,secret,{"sn":device["sn"]})
        prefix=f"DELTA2 #{d2}" if model=="DELTA 2" else "DELTA Pro 3"
        fields=("pd.soc","bms_bmsStatus.soc","bms_slave.soc","bms_emsStatus.f32LcdShowSoc","bms_emsStatus.lcdShowSoc") if model=="DELTA 2" else ("cmsBattSoc","bmsBattSoc","cmsBattFullEnergy","bmsDesignCap","plugInInfo4p81InFlag","plugInInfo4p82InFlag")
        print(prefix)
        for field in fields:
            x=nested_get(quota,field)
            if isinstance(x,(int,float)) and not isinstance(x,bool):
                print(f"   {field} = {x:.3f}")
if __name__=="__main__":main()
