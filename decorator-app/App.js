import React, { useEffect, useState, useCallback } from 'react';
import {
  SafeAreaView,
  ScrollView,
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Share,
  Alert,
  Platform,
  KeyboardAvoidingView,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEY = 'decorator.calc.v1';

const C = {
  bg: '#0b0b0f',
  card: '#16161d',
  card2: '#1e1e27',
  line: '#2a2a35',
  field: '#101017',
  text: '#f4f4f6',
  muted: '#9a9aa8',
  accent: '#ff5c8a',
  accent2: '#ffb15c',
};

const toNum = (v) => {
  const n = parseFloat(String(v).replace(',', '.'));
  return Number.isFinite(n) && n >= 0 ? n : 0;
};

const fmt = (n) =>
  new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(Math.round(n)) + ' ₽';

const emptyItem = () => ({ name: '', qty: '1', price: '0' });

const defaultState = () => ({
  items: [emptyItem()],
  markup: '0',
  labor: '0',
  delivery: '0',
  discount: '0',
});

export default function App() {
  const [state, setState] = useState(defaultState());
  const [loaded, setLoaded] = useState(false);

  // Загрузка из памяти устройства
  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(STORAGE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (parsed && Array.isArray(parsed.items) && parsed.items.length) {
            setState({ ...defaultState(), ...parsed });
          }
        }
      } catch (_) {}
      setLoaded(true);
    })();
  }, []);

  // Сохранение
  useEffect(() => {
    if (!loaded) return;
    AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(state)).catch(() => {});
  }, [state, loaded]);

  const updateItem = useCallback((i, field, value) => {
    setState((s) => {
      const items = s.items.slice();
      items[i] = { ...items[i], [field]: value };
      return { ...s, items };
    });
  }, []);

  const addItem = useCallback(() => {
    setState((s) => ({ ...s, items: [...s.items, emptyItem()] }));
  }, []);

  const removeItem = useCallback((i) => {
    setState((s) => {
      const items = s.items.filter((_, idx) => idx !== i);
      return { ...s, items: items.length ? items : [emptyItem()] };
    });
  }, []);

  const setParam = useCallback((field, value) => {
    setState((s) => ({ ...s, [field]: value }));
  }, []);

  // Расчёт
  const materials = state.items.reduce((a, it) => a + toNum(it.qty) * toNum(it.price), 0);
  const markup = materials * (toNum(state.markup) / 100);
  const labor = toNum(state.labor);
  const delivery = toNum(state.delivery);
  const beforeDiscount = materials + markup + labor + delivery;
  const discount = beforeDiscount * (toNum(state.discount) / 100);
  const grand = beforeDiscount - discount;

  const reset = () => {
    Alert.alert('Очистить смету?', 'Все позиции и параметры будут сброшены.', [
      { text: 'Отмена', style: 'cancel' },
      { text: 'Очистить', style: 'destructive', onPress: () => setState(defaultState()) },
    ]);
  };

  const share = async () => {
    const lines = ['Смета оформления', ''];
    state.items.forEach((it) => {
      if (!toNum(it.qty) && !toNum(it.price) && !it.name) return;
      lines.push(
        `• ${it.name || 'Позиция'} — ${toNum(it.qty)} × ${fmt(toNum(it.price))} = ${fmt(
          toNum(it.qty) * toNum(it.price)
        )}`
      );
    });
    lines.push('');
    lines.push(`Материалы: ${fmt(materials)}`);
    if (markup) lines.push(`Наценка: ${fmt(markup)}`);
    if (labor) lines.push(`Работа: ${fmt(labor)}`);
    if (delivery) lines.push(`Доставка: ${fmt(delivery)}`);
    if (discount) lines.push(`Скидка: −${fmt(discount)}`);
    lines.push(`ИТОГО К ОПЛАТЕ: ${fmt(grand)}`);
    try {
      await Share.share({ message: lines.join('\n') });
    } catch (_) {}
  };

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={styles.h1}>Калькулятор декоратора</Text>
          <Text style={styles.subtitle}>Быстрый расчёт сметы оформления</Text>

          {/* Позиции */}
          <View style={styles.card}>
            <Text style={styles.cardTitle}>ПОЗИЦИИ (МАТЕРИАЛЫ И УСЛУГИ)</Text>
            {state.items.map((item, i) => (
              <View key={i} style={styles.item}>
                <View style={styles.itemTop}>
                  <TextInput
                    style={styles.itemName}
                    placeholder="Например: пионовидные розы"
                    placeholderTextColor={C.muted}
                    value={item.name}
                    onChangeText={(v) => updateItem(i, 'name', v)}
                  />
                  <TouchableOpacity style={styles.iconBtn} onPress={() => removeItem(i)}>
                    <Text style={styles.iconBtnText}>✕</Text>
                  </TouchableOpacity>
                </View>
                <View style={styles.itemGrid}>
                  <View style={styles.miniField}>
                    <Text style={styles.miniLabel}>Кол-во</Text>
                    <TextInput
                      style={styles.fieldInput}
                      keyboardType="decimal-pad"
                      value={String(item.qty)}
                      onChangeText={(v) => updateItem(i, 'qty', v)}
                    />
                  </View>
                  <View style={styles.miniField}>
                    <Text style={styles.miniLabel}>Цена за ед., ₽</Text>
                    <TextInput
                      style={styles.fieldInput}
                      keyboardType="decimal-pad"
                      value={String(item.price)}
                      onChangeText={(v) => updateItem(i, 'price', v)}
                    />
                  </View>
                </View>
                <Text style={styles.itemSum}>
                  Сумма:{' '}
                  <Text style={styles.itemSumValue}>
                    {fmt(toNum(item.qty) * toNum(item.price))}
                  </Text>
                </Text>
              </View>
            ))}
            <TouchableOpacity style={styles.btnAdd} onPress={addItem}>
              <Text style={styles.btnAddText}>+ Добавить позицию</Text>
            </TouchableOpacity>
          </View>

          {/* Параметры */}
          <View style={styles.card}>
            <Text style={styles.cardTitle}>ПАРАМЕТРЫ</Text>
            <ParamRow
              label="Наценка на материалы"
              unit="%"
              value={state.markup}
              onChange={(v) => setParam('markup', v)}
            />
            <ParamRow
              label="Работа / монтаж"
              unit="₽"
              value={state.labor}
              onChange={(v) => setParam('labor', v)}
            />
            <ParamRow
              label="Доставка"
              unit="₽"
              value={state.delivery}
              onChange={(v) => setParam('delivery', v)}
            />
            <ParamRow
              label="Скидка клиенту"
              unit="%"
              value={state.discount}
              onChange={(v) => setParam('discount', v)}
              last
            />
          </View>

          {/* Итоги */}
          <View style={styles.card}>
            <Text style={styles.cardTitle}>ИТОГО</Text>
            <TotalLine label="Материалы" value={fmt(materials)} />
            <TotalLine label="Наценка" value={fmt(markup)} />
            <TotalLine label="Работа" value={fmt(labor)} />
            <TotalLine label="Доставка" value={fmt(delivery)} />
            <TotalLine label="Скидка" value={'−' + fmt(discount)} />
            <View style={styles.grand}>
              <Text style={styles.grandLabel}>К ОПЛАТЕ</Text>
              <Text style={styles.grandValue}>{fmt(grand)}</Text>
            </View>
          </View>

          <Text style={styles.hint}>Данные сохраняются на этом устройстве.</Text>
        </ScrollView>

        {/* Нижняя панель */}
        <View style={styles.bottomBar}>
          <TouchableOpacity style={styles.bShare} onPress={share}>
            <Text style={styles.bShareText}>Поделиться сметой</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.bReset} onPress={reset}>
            <Text style={styles.bResetText}>Сброс</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function ParamRow({ label, unit, value, onChange, last }) {
  return (
    <View style={[styles.row, last && { borderBottomWidth: 0 }]}>
      <Text style={styles.rowLabel}>{label}</Text>
      <View style={styles.rowCtl}>
        <TextInput
          style={styles.rowInput}
          keyboardType="decimal-pad"
          value={String(value)}
          onChangeText={onChange}
        />
        <Text style={styles.rowUnit}>{unit}</Text>
      </View>
    </View>
  );
}

function TotalLine({ label, value }) {
  return (
    <View style={styles.totalLine}>
      <Text style={styles.totalLabel}>{label}</Text>
      <Text style={styles.totalValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  scroll: { padding: 16, paddingBottom: 120, maxWidth: 600, width: '100%', alignSelf: 'center' },
  h1: { color: C.text, fontSize: 26, fontWeight: '800', marginTop: 4 },
  subtitle: { color: C.muted, fontSize: 14, marginTop: 2, marginBottom: 16 },

  card: {
    backgroundColor: C.card,
    borderColor: C.line,
    borderWidth: 1,
    borderRadius: 18,
    padding: 14,
    marginBottom: 14,
  },
  cardTitle: {
    color: C.muted,
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1,
    marginBottom: 12,
  },

  item: {
    backgroundColor: C.card2,
    borderColor: C.line,
    borderWidth: 1,
    borderRadius: 14,
    padding: 12,
    marginBottom: 10,
  },
  itemTop: { flexDirection: 'row', alignItems: 'center', marginBottom: 10 },
  itemName: { flex: 1, color: C.text, fontSize: 17, fontWeight: '600', paddingVertical: 6 },
  itemGrid: { flexDirection: 'row', gap: 8 },
  miniField: { flex: 1 },
  miniLabel: { color: C.muted, fontSize: 11, marginBottom: 4, paddingLeft: 4 },
  fieldInput: {
    backgroundColor: C.field,
    borderColor: C.line,
    borderWidth: 1,
    borderRadius: 11,
    color: C.text,
    paddingHorizontal: 12,
    paddingVertical: 11,
    fontSize: 17,
  },
  itemSum: { marginTop: 10, textAlign: 'right', color: C.muted, fontSize: 15 },
  itemSumValue: { color: C.text, fontSize: 17, fontWeight: '600' },

  iconBtn: {
    width: 34,
    height: 34,
    borderRadius: 17,
    borderColor: C.line,
    borderWidth: 1,
    backgroundColor: C.field,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 8,
  },
  iconBtnText: { color: C.muted, fontSize: 16 },

  btnAdd: {
    borderRadius: 14,
    borderColor: C.accent,
    borderWidth: 1,
    borderStyle: 'dashed',
    backgroundColor: 'rgba(255,92,138,0.08)',
    paddingVertical: 15,
    alignItems: 'center',
  },
  btnAddText: { color: C.accent, fontSize: 17, fontWeight: '700' },

  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 11,
    borderBottomColor: C.line,
    borderBottomWidth: 1,
  },
  rowLabel: { color: C.text, fontSize: 16, flex: 1 },
  rowCtl: { flexDirection: 'row', alignItems: 'center' },
  rowInput: {
    backgroundColor: C.field,
    borderColor: C.line,
    borderWidth: 1,
    borderRadius: 11,
    color: C.text,
    paddingHorizontal: 12,
    paddingVertical: 9,
    fontSize: 17,
    width: 110,
    textAlign: 'right',
  },
  rowUnit: { color: C.muted, fontSize: 14, width: 22, textAlign: 'center' },

  totalLine: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 7 },
  totalLabel: { color: C.muted, fontSize: 15 },
  totalValue: { color: C.text, fontSize: 15, fontWeight: '600' },
  grand: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 10,
    paddingTop: 14,
    borderTopColor: C.line,
    borderTopWidth: 1,
  },
  grandLabel: { color: C.text, fontSize: 16, fontWeight: '700' },
  grandValue: { color: C.accent, fontSize: 30, fontWeight: '800' },

  hint: { color: C.muted, fontSize: 12, textAlign: 'center', marginTop: 4 },

  bottomBar: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    flexDirection: 'row',
    gap: 10,
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 28,
    backgroundColor: 'rgba(11,11,15,0.96)',
    borderTopColor: C.line,
    borderTopWidth: 1,
  },
  bShare: {
    flex: 1,
    backgroundColor: C.accent,
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: 'center',
  },
  bShareText: { color: '#fff', fontSize: 15, fontWeight: '700' },
  bReset: {
    backgroundColor: C.card2,
    borderColor: C.line,
    borderWidth: 1,
    borderRadius: 14,
    paddingVertical: 14,
    paddingHorizontal: 18,
    alignItems: 'center',
  },
  bResetText: { color: C.muted, fontSize: 15, fontWeight: '700' },
});
