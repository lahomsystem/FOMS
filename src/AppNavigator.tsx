import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import CalculatorScreen from './screens/CalculatorScreen';
import EstimatesScreen from './screens/EstimatesScreen';
import SettingsScreen from './screens/SettingsScreen';

export type RootStackParamList = {
  Calculator: undefined;
  Estimates: undefined;
  Settings: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function AppNavigator() {
  return (
    <NavigationContainer>
      <Stack.Navigator initialRouteName="Calculator">
        <Stack.Screen name="Calculator" component={CalculatorScreen} options={{ title: '계산기' }} />
        <Stack.Screen name="Estimates" component={EstimatesScreen} options={{ title: '견적 목록' }} />
        <Stack.Screen name="Settings" component={SettingsScreen} options={{ title: '설정' }} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}


